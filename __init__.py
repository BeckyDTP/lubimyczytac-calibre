#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
"""
Wtyczka calibre pobierająca metadane i okładki z serwisu LubimyCzytać.pl.

Plik główny wtyczki. Zawiera:

* klasę ``LubimyCzytac`` (podklasa ``calibre.ebooks.metadata.sources.base.Source``)
  – punkt wejścia wtyczki: budowanie zapytania do wyszukiwarki LC, analiza
  listy wyników, wybór kandydatów i uruchomienie wątków ``Worker``
  (``worker.py``), które pobierają szczegóły pojedynczych książek;
* klasę ``MetadataCompareKeyGen`` – klucz sortowania wyników według
  trafności (własna odmiana mechanizmu wbudowanego w calibre);
* zestaw testów uruchamianych poleceniem ``calibre-debug -e __init__.py``.

Okno konfiguracji i klucze ustawień znajdują się w ``config.py``.

Dokumentacja API wtyczek calibre: https://manual.calibre-ebook.com/plugins.html

Uwaga dla współautorów: wtyczka deklaruje zgodność z calibre od wersji 3.48
(ostatnia wersja działająca na Pythonie 2). W kodzie nie używamy więc składni
dostępnej wyłącznie w Pythonie 3 (f-stringi, adnotacje typów itp.), a napisy
unicode importujemy przez ``six.text_type``.
"""
from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Roman Cupisz <roman.cupisz+calibre@gmail.com>, 2015-2026 enhancements by Becky <becky@fr.pl>'
__docformat__ = 'restructuredtext en'

# Numer wersji wtyczki (krotka wymagana przez calibre). Zmieniamy go tylko tutaj –
# tekstowa postać (PLUGIN_VERSION w klasie LubimyCzytac) jest wyliczana z tej krotki.
PLUGINVER = (2, 4, 2)

import sys, time, re, threading

try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote

try:
    from queue import Empty, Queue
except ImportError:
    from Queue import Empty, Queue
from six import text_type as unicode

from lxml.html import fromstring

from calibre import as_unicode
from calibre import prints
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.icu import lower
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.localization import get_udc
from calibre.constants import numeric_version
from calibre.constants import DEBUG

from functools import total_ordering
from polyglot.builtins import cmp

# Punkt odniesienia dla znaczników czasu wypisywanych przez debug_print()
BASE_TIME = None


def debug_print(*args):
    """
    Wypisuje komunikat diagnostyczny na konsolę calibre, poprzedzony czasem
    (w sekundach) od pierwszego wywołania.

    Działa tylko wtedy, gdy calibre uruchomiono w trybie debug
    (``calibre-debug -g``); w normalnej pracy nie robi nic.
    """
    global BASE_TIME
    if BASE_TIME is None:
        BASE_TIME = time.time()
    if DEBUG:
        prints('DEBUG: %6.1f'%(time.time()-BASE_TIME), *args)

try:
    load_translations()
except NameError:
    pass  # load_translations() istnieje od calibre 1.9


# Porównywanie obiektów Metadata pod względem trafności {{{

# Rodzajniki pomijane przy porównywaniu tytułów (odziedziczone z calibre –
# dla polskich tytułów nie mają znaczenia, ale nie szkodzą).
words = ("the", "a", "an", "of", "and")
prefix_pat = re.compile(r'^(%s)\s+'%("|".join(words)))
trailing_paren_pat = re.compile(r'\(.*\)$')
whitespace_pat = re.compile(r'\s+')

def cleanup_title(s):
    """
    Normalizuje tytuł na potrzeby porównań w ``MetadataCompareKeyGen``:
    małe litery, bez początkowego rodzajnika, bez końcowego nawiasu
    (np. „(tom 2)”), z pojedynczymi odstępami.
    """
    if not s:
        s = _('Unknown')
    s = s.strip().lower()
    s = prefix_pat.sub(' ', s)
    s = trailing_paren_pat.sub('', s)
    s = whitespace_pat.sub(' ', s)
    return s.strip()


def detect_download_mode():
    """
    Rozpoznaje, skąd calibre wywołało ``identify()``:

    * ``'single'``  – okno „Pobierz metadane” dla jednej książki
      (funkcja ``single_identify`` w ``calibre.ebooks.metadata.sources.worker``);
    * ``'bulk'``    – pobieranie masowe (funkcja ``main`` w tym samym module);
    * ``'unknown'`` – nic nie rozpoznano (np. testy z ``calibre-debug``,
      pobieranie samej okładki, inna wersja calibre).

    Wtyczka działa we własnym wątku, więc na własnym stosie niczego nie
    zobaczy – zaglądamy w stos wątku głównego procesu roboczego calibre
    (``sys._current_frames``). Nazwy obu funkcji są wewnętrzne dla calibre,
    ale nie zmieniły się od 2011 roku; każdy błąd lub brak rozpoznania daje
    ``'unknown'``, więc wykrycie nigdy nie może zepsuć pobierania.

    Po co: w trybie masowym calibre stosuje pierwszy wynik bez pokazywania
    listy, dlatego wirtualny wynik z podpowiedzią (``_manual_search_result``)
    wolno dodać tylko w oknie pojedynczego pobierania.
    """
    try:
        if hasattr(threading, 'main_thread'):
            main = threading.main_thread()
        else:
            # Python 2 (calibre 3.48) nie ma threading.main_thread()
            main = None
            for t in threading.enumerate():
                if isinstance(t, threading._MainThread):
                    main = t
                    break
        frame = sys._current_frames().get(main.ident) if main is not None else None
        while frame is not None:
            name = frame.f_code.co_name
            module = frame.f_globals.get('__name__', '')
            if module.endswith('metadata.sources.worker'):
                if name == 'single_identify':
                    return 'single'
                if name == 'main':
                    return 'bulk'
            frame = frame.f_back
    except Exception:
        pass
    return 'unknown'



@total_ordering
class MetadataCompareKeyGen:

    """
    Klucz sortowania wyników ``identify`` według trafności względem zapytania
    (tytuł, autorzy, identyfikatory). Służy wyłącznie do porządkowania
    wyników pochodzących z tej wtyczki – nie do porównań między różnymi
    źródłami metadanych.

    Sortowanie rosnące po tym kluczu daje kolejność od najtrafniejszego
    wyniku. Każdy element krotki ``base`` przyjmuje wartość 1 (pasuje)
    lub 2 (nie pasuje), więc mniejsza krotka oznacza lepszy wynik.

    Jest to zmodyfikowana kopia klasy ``InternalMetadataCompareKeyGen``
    z calibre. Różnica polega na kolejności kryteriów – calibre w pierwszej
    kolejności premiuje zgodny identyfikator i okładkę, my natomiast:

    1. dokładną zgodność tytułu,
    2. zgodność numeru ISBN,
    3. zawieranie się szukanego tytułu w tytule wyniku,
    4. liczbę zgodnych nazwisk autorów (im więcej, tym lepiej),
    5. wypełnienie wszystkich pól,
    6. dostępność okładki w pamięci podręcznej.

    Przy równych krotkach ``base`` wygrywa wynik z wyraźnie (o ponad 10%)
    dłuższym opisem, a w ostateczności pozycja kandydata na liście
    ułożonej przez ``_parse_search_results`` (``source_relevance``).
    """

    def __init__(self, mi, source_plugin, title, authors, identifiers):
        """
        :param mi: porównywany obiekt ``Metadata`` (może być ``None``)
        :param source_plugin: instancja wtyczki (potrzebna do sprawdzenia pól i okładki)
        :param title: tytuł z zapytania użytkownika
        :param authors: lista autorów z zapytania użytkownika
        :param identifiers: słownik identyfikatorów z zapytania (interesuje nas ``isbn``)
        """
        if not mi:
            self.base = (2,2,2,2,2)
            self.comments_len = 0
            self.extra = 0
            return

        isbn = 1 if mi.isbn and identifiers.get('isbn', None) is not None \
                and mi.isbn == identifiers.get('isbn', None) else 2

        all_fields = 1 if source_plugin.test_fields(mi) is None else 2

        cl_title = cleanup_title(title)
        cl_title_mi = cleanup_title(mi.title)
        exact_title = 1 if title and \
                cl_title == cl_title_mi else 2

        contains_title = 1 if title and \
                cl_title in cl_title_mi else 2

        # Porównujemy same nazwiska (ostatni człon nazwy autora)
        auths = []
        if authors:
            for a in authors:
                auths.append(a.split(" ")[-1])
        miauths = []
        for a in mi.authors:
            miauths.append(a.split(" ")[-1])

        author_segments = list(set(miauths) & set(auths))

        has_cover = 2 if (not source_plugin.cached_cover_url_is_reliable or
                source_plugin.get_cached_cover_url(mi.identifiers) is None) else 1

        self.base = (exact_title, isbn, contains_title, -len(author_segments), all_fields, has_cover)

        self.comments_len = len(mi.comments.strip() if mi.comments else '')
        self.extra = (getattr(mi, 'source_relevance', 0), )


    def compare_to_other(self, other):
        """
        Porównuje dwa klucze. Zwraca -1, 0 lub 1 tak jak klasyczna funkcja ``cmp``.
        Najpierw rozstrzyga krotka ``base``, potem długość opisu (jeśli różnica
        przekracza 10% ich łącznej długości), na końcu ``source_relevance``.
        """
        a = cmp(self.base, other.base)
        if a != 0:
            return a
        cx, cy = self.comments_len, other.comments_len
        if cx and cy:
            t = (cx + cy) / 20
            delta = cy - cx
            if abs(delta) > t:
                return -1 if delta < 0 else 1
        return cmp(self.extra, other.extra)

    # Operatory porównania wymagane przez sortowanie (uzupełniane przez @total_ordering)

    def __eq__(self, other):
        return self.compare_to_other(other) == 0

    def __ne__(self, other):
        return self.compare_to_other(other) != 0

    def __lt__(self, other):
        return self.compare_to_other(other) < 0

    def __le__(self, other):
        return self.compare_to_other(other) <= 0

    def __gt__(self, other):
        return self.compare_to_other(other) > 0

    def __ge__(self, other):
        return self.compare_to_other(other) >= 0


# }}}



class LubimyCzytac(Source):
    """
    Źródło metadanych calibre dla serwisu LubimyCzytać.pl.

    Przebieg pobierania metadanych (``identify``):

    1. Jeśli książka ma już identyfikator ``lubimyczytac`` – od razu
       pobieramy jej stronę, bez korzystania z wyszukiwarki.
    2. W przeciwnym razie przeszukujemy LC (``_search``): kolejne warianty
       zapytania (``_query_variants`` → ``create_query``) i analiza listy
       wyników (``_parse_search_results``), aż do znalezienia wyniku
       zgodnego z tytułem i autorem.
    3. Dla każdego kandydata uruchamiamy wątek ``Worker`` (``worker.py``),
       który pobiera i parsuje stronę książki, a gotowy obiekt ``Metadata``
       wkłada do kolejki wyników.
    """

    name                    = 'LubimyCzytac'
    description             = _('Download book metadata and covers from LubimyCzytac.pl')
    author                  = 'Roman Cupisz, enhancements and code maintenance by Becky'
    version                 = PLUGINVER
    minimum_calibre_version = (3, 48, 0)

    capabilities = frozenset(['identify', 'cover'])
    # Pola metadanych, które wtyczka potrafi wypełnić (calibre pokazuje je
    # m.in. w konfiguracji źródeł metadanych)
    touched_fields = frozenset(['title', 'authors', 'identifier:lubimyczytac',
        'identifier:isbn', 'rating', 'comments', 'publisher', 'pubdate',
        'series', 'tags', 'languages'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True
    prefer_results_with_isbn = False

    PLUGIN_VERSION = ".".join([str(x) for x in version])
    CALIBRE_VERSION = ".".join([str(x) for x in numeric_version])

    ID_NAME   = 'lubimyczytac'    # nazwa identyfikatora w metadanych calibre
    BASE_URL  = 'https://lubimyczytac.pl'
    BOOK_PATH = '/ksiazka/'
    # LC akceptuje dowolny tekst po ID książki (slug), więc zamiast prawdziwego
    # sluga doklejamy stały przyrostek
    BOOK_ADD = '/ksiazka'

    # Tekst wyświetlany na górze okna konfiguracji: wersja calibre, wersja
    # wtyczki i link do wątku na forum MobileRead
    config_help_message = "<p>"+_('Calibre')+": <b>"+CALIBRE_VERSION+"</b> • \
        "+_('Plugin version')+": <b>"+PLUGIN_VERSION+"</b> • "+_('Please ' \
        'report bugs through the <a href="https://www.mobileread.com/forums/showthread.php?t=282922">MobileRead</a> forum.')

    def config_widget(self):
        """
        Zwraca własne okno konfiguracji wtyczki (zamiast domyślnego z calibre).
        Import jest wykonywany tutaj, by nie ładować Qt przy każdym imporcie wtyczki.
        """
        from .config import ConfigWidget
        return ConfigWidget(self)

    def get_book_url(self, identifiers):
        """
        Buduje adres strony książki na podstawie identyfikatora ``lubimyczytac``.
        Calibre używa go m.in. do linku „Pokaż książkę w LubimyCzytac” w panelu
        szczegółów. Zwraca krotkę ``(nazwa_identyfikatora, wartość, url)``
        albo ``None``, gdy identyfikatora brak.
        """
        lubimy_czytac_id = identifiers.get(self.ID_NAME, None)
        if lubimy_czytac_id:
            return (self.ID_NAME, lubimy_czytac_id,
                    '%s%s%s%s'%(LubimyCzytac.BASE_URL, LubimyCzytac.BOOK_PATH, lubimy_czytac_id, LubimyCzytac.BOOK_ADD))

    def id_from_url(self, url):
        """
        Operacja odwrotna do ``get_book_url``: wyciąga identyfikator LC
        z wklejonego adresu strony książki lub audiobooka. Dzięki temu
        użytkownik może wkleić URL w pole identyfikatorów w calibre.
        """
        match = re.match(r'%s/(ksiazka|audiobook)/(\d+)/.*' % LubimyCzytac.BASE_URL, url)
        if match:
            return (self.ID_NAME, match.group(2))
        return None


    def identify_results_keygen(self, title=None, authors=None,
            identifiers={}):
        """
        Zwraca funkcję generującą klucz sortowania wyników ``identify``
        według trafności (patrz ``MetadataCompareKeyGen``). Calibre wywołuje
        ją, by uporządkować listę wyników pokazywaną użytkownikowi.
        """

        def keygen(mi):
            return MetadataCompareKeyGen(mi, self, title, authors,
                identifiers)
        return keygen


    def becky_get_author_tokens(self, log, authors, only_first_author=True):
        """
        Dzieli nazwy autorów na tokeny przydatne w zapytaniu do wyszukiwarki.
        Zmodyfikowana kopia ``Source.get_author_tokens`` z calibre.

        Zasady:

        * jeśli w nazwie jest przecinek, zakładamy zapis „Nazwisko, Imię”
          i przestawiamy człony na „Imię Nazwisko”;
        * partykuły „von” i „van” sklejamy z nazwiskiem w jeden token,
          żeby nazwisko nie rozpadło się na dwa człony;
        * pomijamy tokeny krótsze niż 3 znaki (inicjały) oraz „Unknown”;
        * apostrof zostaje (nazwiska irlandzkie, np. O'Brien).

        Zwraca generator tokenów.
        """

        if authors:
            remove_pat = re.compile(r'[!@#$%^&*()（）「」{}`~"\[\]/]')
            replace_pat = re.compile(r'[+.:;,，。；：]')
            if only_first_author:
                authors = authors[:1]
            for au in authors:
                has_comma = ',' in au
                au = replace_pat.sub(' ', au)
                parts = au.split()
                if has_comma:
                    # Zapis „Nazwisko, Imię” – przenosimy nazwisko na koniec
                    parts = parts[1:] + parts[:1]

                if len(parts) > 1:
                    if parts[-2] == "von" or parts[-2] == "van":
                        parts[-1] = parts[-2] + " " + parts[-1]
                        del parts[-2]
                for tok in parts:
                    tok = remove_pat.sub('', tok).strip()
                    if len(tok) > 2 and tok.lower() not in (
                            _('Unknown').lower()):
                        yield tok


    def create_query(self, log, title=None, authors=None):
        """
        Buduje adres zapytania do wyszukiwarki LC na podstawie tytułu
        i (opcjonalnie) autorów. Zwraca ``None``, gdy z podanych danych
        nie da się zbudować sensownego zapytania.

        Wyszukiwarka LC działa dobrze tylko dla prostych fraz, dlatego tytuł
        jest mocno upraszczany – każda z poniższych reguł powstała w odpowiedzi
        na konkretny problem zgłoszony przez użytkowników.

        Autorzy: do zapytania trafia wyłącznie nazwisko pierwszego autora
        (ostatni człon nazwy, a przy włączonej opcji „Nazwisko Imię” – pierwszy).
        Gdy w konfiguracji zaznaczono „LC website has search engine issues”,
        autor jest pomijany całkowicie i szukamy wyłącznie po tytule.
        """
        q = ''
        # ta = 1 oznacza, że do zapytania trafił już człon z nazwiskiem autora
        # (przed tytułem trzeba wtedy wstawić separator)
        ta=0

        from . import config as cfg
        swapnames = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.SWAP_NAMES, cfg.DEFAULT_STORE_VALUES[cfg.SWAP_NAMES])
        LCissue = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.LC_ISSUE, cfg.DEFAULT_STORE_VALUES[cfg.LC_ISSUE])

        if authors:
            author_tokens = list(self.becky_get_author_tokens(log, authors,
                    only_first_author=True))
            if author_tokens:
                tokens = [quote(t.encode('utf-8') if isinstance(t, unicode) else t) for t in author_tokens]

                if not swapnames:
                    # Zapis „Imię Nazwisko” – nazwiskiem jest ostatni człon
                    ostatni_czlon = tokens[-1:]
                    if len(ostatni_czlon) > 0:
                        ta=1
                        q += '+'.join(ostatni_czlon)
                else:
                    # Zapis „Nazwisko Imię” – nazwiskiem jest pierwszy człon
                    ostatni_czlon = tokens[0]
                    if len(ostatni_czlon) > 0:
                        ta=1
                        q += ''.join(ostatni_czlon)

        # Opcja „LC website has search engine issues”: szukamy tylko po tytule
        if (LCissue == 1):
            q= ''
            ta=0   # bez autora w zapytaniu nie ma czego oddzielać od tytułu

        if title:
            title = title.replace('?','')
            title = title.replace('_',' ')

            # Cudzysłowy mają kolosalne znaczenie dla wyszukiwarki LC – dla
            # uproszczenia bierzemy z tytułu tylko fragment przed pierwszym
            # cudzysłowem (prostym lub zapisanym jako dwa przecinki)
            if '\"' in title or ',,' in title:
                title = title.split('"')[0].split(',,')[0]

            # Błąd LC: wyszukiwarka nie radzi sobie z ampersandem (&),
            # więc szukamy tylko tego, co jest przed nim
            if '&' in title:
                title = title.split('&')[0]

            # Usuwamy hash (#) z tytułu
            if "#" in title:
                title = title.replace('#','')

            # Usuwamy nawiasy z tytułu (zawartość zostaje)
            if "(" in title:
                title = title.replace('(','')
            if ")" in title:
                title = title.replace(')','')

            # Apostrofy: LC nie jest konsekwentne w ich zapisie (prosty vs.
            # typograficzny), a zamiana jednego na drugi nie rozwiązywała
            # problemu – dlatego szukamy tylko fragmentu przed apostrofem
            if "'" in title:
                title = title.split('\'')[0]

            # Dywiz otoczony spacjami zamieniamy na trzy gwiazdki, aby
            # przetrwał podział na tokeny (get_title_tokens by go wyciął);
            # poniżej zamieniamy go z powrotem
            if " - " in title:
                title = title.replace(' - ',' *** ')

            # Ukośnik (slash) bez spacji wokół – np. „08/15” – zepsułby
            # standardowe tokenizowanie, więc dzielimy tytuł ręcznie
            if "/" in title and not " / " in title:
                title_tokens = [token for token in title.lower().split(' ') if len(token)>1]
            else:
                title_tokens = list(self.get_title_tokens(title,
                               strip_joiners=False, strip_subtitle=True))


            if title_tokens:
                # Przywracamy dywiz w miejsce trzech gwiazdek
                if "***" in title_tokens:
                    title_tokens = self.replaceInList(title_tokens,"***","-")
                if ta==1:
                    q += '%20'
                tokens = [quote(t.encode('utf-8') if isinstance(t, unicode) else t) for t in title_tokens]
                q = q + '%20'.join(tokens)
        if not q:
            return None
        return 'https://lubimyczytac.pl/szukaj/ksiazki?phrase=' + q

    def get_cached_cover_url(self, identifiers):
        """
        Zwraca adres okładki zapamiętany w pamięci podręcznej wtyczki dla
        podanych identyfikatorów (bezpośrednio po ID LC albo pośrednio –
        przez ISBN zmapowany na ID LC). Adresy trafiają do pamięci podręcznej
        w ``Worker.parse_details``.
        """
        url = None
        lubimy_czytac_id = identifiers.get(self.ID_NAME, None)
        if lubimy_czytac_id is None:
            isbn = identifiers.get('isbn', None)
            if isbn is not None:
                lubimy_czytac_id = self.cached_isbn_to_identifier(isbn)
        if lubimy_czytac_id is not None:
            url = self.cached_identifier_to_cover_url(lubimy_czytac_id)
        return url

    def cached_identifier_to_cover_url(self, id_):
        """
        Odczyt adresu okładki z pamięci podręcznej (pod blokadą). Gdy brak
        wpisu dla ID, próbuje jeszcze wariantu ``small/<ID>``.
        """
        with self.cache_lock:
            url = self._get_cached_identifier_to_cover_url(id_)
            if not url:
                url = self._get_cached_identifier_to_cover_url('small/'+id_)
            return url

    def _get_cached_identifier_to_cover_url(self, id_):
        """Surowy odczyt z pamięci podręcznej – wywoływać tylko pod ``cache_lock``."""
        url = self._identifier_to_cover_url_cache.get(id_, None)
        return url

    def identify(self, log, result_queue, abort, title=None, authors=None,
        identifiers={}, timeout=30):
        """
        Główna metoda wtyczki wywoływana przez calibre: znajduje kandydatów
        i uruchamia wątki ``Worker``, które wkładają gotowe obiekty
        ``Metadata`` do ``result_queue``.

        Gdy książka ma identyfikator ``lubimyczytac``, pomijamy wyszukiwarkę
        i od razu pobieramy stronę książki. W przeciwnym razie przeszukujemy
        LC według strategii opisanej w ``_search`` (kilka wariantów zapytania,
        aż do znalezienia wyniku zgodnego z tytułem i autorem).

        Autorzy do porównywania wyników są sprowadzani do konwencji LC
        („Imię Nazwisko”) – przy włączonej opcji „Nazwisko Imię” przestawiamy
        człony funkcją ``swap_names``. Do budowania zapytania ``create_query``
        dostaje autorów w oryginalnym zapisie i sam wybiera nazwisko.

        Wyniki Workerów trafiają najpierw do własnej kolejki: po pobraniu stron
        znamy pełne listy autorów (kafelek wyników LC pokazuje najwyżej dwóch),
        więc ``_filter_results_by_authors`` może odrzucić kandydatów bez
        zgodnego autora, zanim wyniki trafią do calibre.
        """
        log.info('--- START ---')
        matches = []
        lubimy_czytac_id = identifiers.get(self.ID_NAME, None)
        log.info('\nTitle: %s\nAuthors: %s\n'%(title, authors))
        br = self.browser

        # Tytuł i autorzy dokładnie tak, jak podało calibre (z diakrytykami) –
        # do wirtualnego wyniku z podpowiedzią, gdy nic nie znajdziemy
        orig_title = title
        orig_authors = list(authors) if authors else None
        download_mode = detect_download_mode()
        log.info('BECKY INFO: tryb pobierania: %s' % download_mode)

        from . import config as cfg
        # Import wewnątrz metody (nie na górze modułu), żeby calibre przy starcie
        # ładowało tylko ten plik; funkcje pomocnicze dzielimy z worker.py zamiast
        # trzymać ich kopie
        from .worker import Worker, swap_names, unique, html_escape

        # Zapisujemy efektywne ustawienia w logu, aby można było odtworzyć
        # konfigurację użytkownika podczas analizy zgłoszonego problemu
        # (etykiety celowo bez polskich znaków – log bywa wklejany na forum).
        prefs = cfg.plugin_prefs[cfg.STORE_NAME]
        config_labels = (
            ('maxDownloads', 'Maksymalna liczba pobieranych wynikow'),
            ('appendasTags', 'Kategorie jako etykiety'),
            ('replaceISBN', 'Zastepuj ISBN'),
            ('fastMatch', 'Szybkie dopasowanie (fastMatch)'),
            ('beforeOtherEditionsExist', 'Informacja o innych wydaniach'),
            ('beforeOtherEditionsAll', 'Pelna lista innych wydan'),
            ('beforeOtherEditionsShort', 'Krotka lista innych wydan'),
            ('beforeHorizontalLine', 'Linia pozioma przed lista wydan'),
            ('appendPages', 'Dolacz liczbe stron'),
            ('appendPagesSimplified', 'Uproszczony zapis liczby stron'),
            ('appendOriginalTitle', 'Dolacz tytul oryginalny'),
            ('appendTranslation', 'Dolacz tlumacza'),
            ('appendSerWyd', 'Dolacz serie wydawnicza'),
            ('appendGenre', 'Dolacz kategorie'),
            ('appendKeywords', 'Dolacz slowa kluczowe'),
            ('appendRating', 'Dolacz ocene LC'),
            ('appendID', 'Dolacz ID LC'),
            ('appendRatingCount', 'Dolacz liczbe ocen'),
            ('appendDateFirstEdition', 'Dolacz date pierwszego wydania'),
            ('appendDateFirstPolishEdition', 'Dolacz date pierwszego polskiego wydania'),
            ('swapNames', 'Zamiana imienia i nazwiska'),
            ('LCissue', 'Tryb diagnostyczny problemow LC'),
            ('preferISBNMatch', 'Preferuj zgodnosc ISBN'),
            ('suggestManualSearch', 'Podpowiedz reczne wyszukanie przy braku wynikow'),
        )
        log.info('--- KONFIGURACJA WTYCZKI LUBIMYCZYTAC ---')
        for key, label in config_labels:
            value = prefs.get(key, cfg.DEFAULT_STORE_VALUES.get(key))
            log.info('KONFIGURACJA: %s = %s (%s)' % (label, value, key))
        log.info('--- KONIEC KONFIGURACJI WTYCZKI ---')

        swapnames = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.SWAP_NAMES, cfg.DEFAULT_STORE_VALUES[cfg.SWAP_NAMES])
        authors_lc = None

        if lubimy_czytac_id:
            # Znamy identyfikator LC – nie ma potrzeby korzystać z wyszukiwarki
            log.info('lubimy_czytac_id exists. Not looking for other editions.')
            matches.append('%s/ksiazka/%s/ksiazka'%(LubimyCzytac.BASE_URL, lubimy_czytac_id))
        else:
            # Zapytanie do wyszukiwarki budujemy z tytułu i autorów bez znaków
            # diakrytycznych – tak samo normalizowane są potem wyniki
            if title is not None:
                title = get_udc().decode(title)
            else:
                title = ''
            if authors is not None:
                authors = [get_udc().decode(a) for a in authors]
            # Autorzy w konwencji LC („Imię Nazwisko”) – do porównywania wyników
            if authors:
                authors_lc = [swap_names(a) for a in authors] if swapnames else list(authors)
                if swapnames:
                    log.info('BECKY INFO: autorzy do porownan (po zamianie Nazwisko Imie): %s' % authors_lc)

            matches = self._search(log, br, title, authors, authors_lc, timeout, abort)

        if abort.is_set():
            return

        if not matches:
            log.error('No matches found for: %r / %r' % (title, authors))
            suggest = prefs.get(cfg.SUGGEST_MANUAL_SEARCH, cfg.DEFAULT_STORE_VALUES[cfg.SUGGEST_MANUAL_SEARCH])
            if suggest and orig_title and download_mode == 'single':
                # Wirtualny wynik z linkami do ręcznego wyszukania – tylko w oknie
                # pojedynczego pobierania (w masowym calibre zastosowałoby go bez pytania)
                log.info('BECKY HINT: dodaje wirtualny wynik z podpowiedzia recznego wyszukania')
                result_queue.put(self._manual_search_result(orig_title, orig_authors, html_escape))
            elif suggest:
                log.info('BECKY INFO: podpowiedz recznego wyszukania pominieta (tryb: %s)' % download_mode)
            return

        # Usuwamy duplikaty z listy kandydatów, zachowując kolejność – ranking
        # ustalony w _parse_search_results decyduje o source_relevance
        if matches and len(matches) > 1:
            log.info('BECKY INFO: matches BEFORE: %d'% len(matches))
            matches = unique(matches)
            log.info('BECKY INFO: matches UNIQUE: %d'% len(matches))

        log.debug('BECKY: Starting workers for:\n%s' % ('\n'.join(matches,)))
        log.debug('BECKY: Przed workers')
        # Opcja „Prefer matching ISBN”: Worker sprawdzi inne wydania kandydata
        # i wybierze to o identycznym ISBN jak w calibre
        prefer_isbn_match = cfg.plugin_prefs[cfg.STORE_NAME].get(
            cfg.PREFER_ISBN_MATCH, cfg.DEFAULT_STORE_VALUES[cfg.PREFER_ISBN_MATCH])
        target_isbn = identifiers.get("isbn") if prefer_isbn_match else None
        if target_isbn:
            log.info('ISBN-EDITION: opcja Prefer matching ISBN jest wlaczona')
        # Indeks kandydata (i) staje się jego source_relevance – ostatnim
        # kryterium sortowania w MetadataCompareKeyGen. Wyniki zbieramy do
        # własnej kolejki, żeby przed oddaniem ich calibre odsiać kandydatów
        # bez zgodnego autora (_filter_results_by_authors).
        collected = Queue()
        workers = [Worker(url, collected, br, log, i, self, target_isbn=target_isbn) for i, url in
                enumerate(matches) if url]
        log.debug('BECKY: Po workers')

        log.info('-------------------------------  BEDA PARSOWANE  -------------------------------')

        for w in workers:
            w.start()
            # Nie wysyłamy wszystkich żądań jednocześnie
            time.sleep(0.1)

        # Czekamy na zakończenie wątków, reagując na przerwanie przez użytkownika
        while not abort.is_set():
            a_worker_is_alive = False
            for w in workers:
                w.join(0.2)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break

        results = []
        while True:
            try:
                results.append(collected.get_nowait())
            except Empty:
                break
        results = self._filter_results_by_authors(log, results, authors_lc)
        for mi in results:
            result_queue.put(mi)

        return None

    def _filter_results_by_authors(self, log, results, authors_lc):
        """
        Po pobraniu stron książek odrzuca kandydatów, których pełna lista
        autorów nie zgadza się z autorami z calibre – pod warunkiem, że
        przynajmniej jeden kandydat się zgadza (inaczej zostawiamy wszystkich,
        bo to LC może inaczej zapisywać autora).

        Potrzebne, bo kafelek wyników wyszukiwarki LC pokazuje najwyżej dwóch
        autorów: przy antologiach autor z calibre bywa czwarty czy dziesiąty
        i na etapie analizy wyników uchodzi za niezgodnego, przez co obok
        właściwej książki trafiają do calibre także inne o podobnym tytule.
        Porównanie tak jak w ``_authors_agree`` (pełna nazwa albo nazwisko),
        odporne na ``fixauthors`` calibre i na opcję „Nazwisko Imię”.
        """
        if not authors_lc or len(results) < 2:
            return results
        user_authors = [lower(get_udc().decode(a)) for a in authors_lc]
        agreeing = []
        for mi in results:
            lc_authors = [lower(get_udc().decode(a)) for a in (mi.authors or [])]
            if self._authors_agree(lc_authors, user_authors):
                agreeing.append(mi)
        if agreeing and len(agreeing) < len(results):
            log.info('BECKY INFO: po pobraniu stron %d z %d kandydatow ma zgodnego autora; pozostalych odrzucam'
                     % (len(agreeing), len(results)))
            for mi in results:
                if mi not in agreeing:
                    log.info('BECKY INFO:   odrzucam: %s | %s' % (mi.identifiers.get('lubimyczytac'), ', '.join(mi.authors or [])))
            return agreeing
        return results

    def _manual_search_hint(self, title, authors, html_escape):
        """
        Buduje HTML podpowiedzi do ręcznego wyszukania książki, gdy LC nic nie
        znalazło. Wyszukiwarka LC zna tylko wydanie główne, ale strony wydań
        wydanych pod innym tytułem są indeksowane przez wyszukiwarki
        internetowe – stąd linki do Google i DuckDuckGo zawężone do
        ``site:lubimyczytac.pl`` oraz do własnej wyszukiwarki LC. Na końcu
        instrukcja, jak wpisać znaleziony identyfikator (``lubimyczytac:<ID>``).
        Panel opisu w oknie pobierania calibre renderuje HTML i otwiera linki
        http/https w przeglądarce. Wszystko w ``_()``, bo to tekst dla użytkownika.
        """
        author = authors[0] if authors else ''
        phrase = ('"%s" %s' % (title, author)).strip()
        def q(text):
            return quote(text.encode('utf-8') if isinstance(text, unicode) else text)
        web_query = q('site:lubimyczytac.pl ' + phrase)
        lc_query = q(('%s %s' % (title, author)).strip())
        parts = [
            '<p><span style="color:red; font-weight:bold;">%s</span> %s</p>' % (
                html_escape(_('WARNING: LubimyCzytac did not find this book.')),
                html_escape(_('This entry is not book metadata - do not apply it.'))),
            '<p>%s</p>' % html_escape(_('The LubimyCzytac search engine knows only the main edition of each book. '
                                        'An edition published under a different title can usually be found with a web search:')),
            '<ul>',
            '<li><a href="https://www.google.com/search?q=%s">%s</a></li>' % (
                web_query, html_escape(_('Search Google (lubimyczytac.pl only)'))),
            '<li><a href="https://duckduckgo.com/?q=%s">%s</a></li>' % (
                web_query, html_escape(_('Search DuckDuckGo (lubimyczytac.pl only)'))),
            '<li><a href="https://lubimyczytac.pl/szukaj/ksiazki?phrase=%s">%s</a></li>' % (
                lc_query, html_escape(_('Search on LubimyCzytac'))),
            '</ul>',
            '<p>%s</p>' % html_escape(_('When you find the page of your edition, copy the number from its address '
                                        '(for example 74063 from lubimyczytac.pl/ksiazka/74063/krol-pozwow), enter '
                                        'lubimyczytac:74063 in the identifiers field of the book and download the metadata again.')),
        ]
        return ''.join(parts)

    def _manual_search_result(self, title, authors, html_escape):
        """
        Wirtualny wynik dla okna pobierania: tytuł i autorzy dokładnie takie,
        jak w calibre (przypadkowe zastosowanie zmieni tylko opis), bez
        identyfikatora LC (ID 0 dałoby zły adres i próbę pobrania okładki),
        a w opisie podpowiedź z ``_manual_search_hint``.
        """
        from calibre.ebooks.metadata.book.base import Metadata
        mi = Metadata(title, authors or [_('Unknown')])
        mi.comments = self._manual_search_hint(title, authors, html_escape)
        mi.source_relevance = 0
        return mi

    def _split_title(self, title):
        """
        Dzieli tytuł na część przed pierwszym separatorem (kropka lub dwukropek)
        i część po nim. Polscy wydawcy zapisują tak zarówno „Tytuł. Podtytuł”,
        jak i „Cykl. Tytuł” (np. „The Naturals. Więzy krwi”, gdzie na LC tytułem
        jest „Więzy krwi”, a „The Naturals” cyklem) – dlatego próbujemy obu
        części. Separatorem jest tylko kropka lub dwukropek, po których
        następuje odstęp albo koniec tytułu, i których nie poprzedza inicjał
        (pojedyncza wielka litera) – kropka w skrótach („cz.1”, „t.2”)
        i w inicjałach („J.R.R.”) nie dzieli tytułu (dla „Czarodziejski
        statek cz.1” powstawało bezsensowne zapytanie „Hobb 1”).
        Zwraca krotkę ``(przed, po)``; pusty człon to ``None``.
        """
        if not title:
            return (None, None)
        # separator: kropka/dwukropek z odstępem (lub końcem) po sobie, ale nie
        # po pojedynczej wielkiej literze (inicjał: „J.R.R. Tolkien”, „Philip K. Dick”)
        m = re.search(r'(?<![A-Z])[.:](?=\s|$)', title)
        if not m:
            return (None, None)
        before = title[:m.start()].strip()
        after = title[m.end():].strip()
        return (before or None, after or None)

    def _query_variants(self, title, authors):
        """
        Kolejność prób wyszukiwania – od najbardziej precyzyjnej. Wyszukiwarka
        LC gubi się przy długich frazach, więc wariantów z nazwiskiem autora
        i krótszym tytułem jest kilka. Zwraca listę krotek
        ``(etykieta_do_logu, tytuł, autorzy_lub_None)``.
        """
        before, after = self._split_title(title)
        variants = []
        if authors:
            variants.append(('autor + pelny tytul', title, authors))
            if before:
                variants.append(('autor + tytul przed separatorem', before, authors))
            if after:
                variants.append(('autor + tytul po separatorze', after, authors))
        variants.append(('tylko pelny tytul', title, None))
        if before:
            variants.append(('tylko tytul przed separatorem', before, None))
        return variants

    def _fetch_search_page(self, log, br, query, timeout):
        """Pobiera stronę wyników wyszukiwarki i zwraca sparsowane drzewo HTML albo ``None`` przy błędzie."""
        try:
            response = br.open_novisit(query, timeout=timeout)
        except Exception as e:
            if callable(getattr(e, 'getcode', None)) and e.getcode() == 404:
                log.error('No matches for identify query (HTTP 404)')
            else:
                log.error('Failed to make identify query: %s' % as_unicode(e))
            return None
        try:
            raw = response.read().strip()
            raw = raw.decode('utf-8', errors='replace')
            if not raw:
                log.error('Failed to get raw result for query')
                return None
            return fromstring(clean_ascii_chars(raw))
        except:
            log.exception('Failed to parse LubimyCzytac.pl page for query')
            return None

    def _search(self, log, br, title, authors, authors_lc, timeout, abort):
        """
        Strategia wyszukiwania: wykonuje kolejne warianty zapytania
        (``_query_variants``) i kończy na pierwszym, który da wynik „mocny”,
        czyli zgodny z tytułem **i** autorem (patrz ``_parse_search_results``).

        Wynik „słaby” (np. same książki o tym tytule, ale innych autorów –
        LC chętnie zwraca takie przy nieudanym zapytaniu) nie kończy
        wyszukiwania; zapamiętujemy go jako rezerwę i próbujemy dalej.
        Gdy żaden wariant nie da wyniku mocnego, zwracamy rezerwę – pierwszą
        niepustą listę kandydatów słabych (zgodny tylko tytuł albo tylko autor).
        Wyniki niezgodne ani z tytułem, ani z autorem nie są kandydatami, więc
        gdy LC nie zna szukanego tytułu, wtyczka kończy bez wyników zamiast
        podsuwać przypadkowe książki. Identyczne zapytania (np. przy opcji
        „LC website has search engine issues”, która usuwa autora z każdego
        wariantu) wykonujemy tylko raz.

        :param authors: autorzy w zapisie z calibre (do zapytania)
        :param authors_lc: autorzy w konwencji LC „Imię Nazwisko” (do porównań)
        :return: lista adresów kandydatów (może być pusta)
        """
        variants = self._query_variants(title, authors)
        weak = []
        tried = set()
        for number, (label, variant_title, variant_authors) in enumerate(variants, 1):
            query = self.create_query(log, title=variant_title, authors=variant_authors)
            if not query:
                log.info('BECKY -- proba %d/%d (%s): brak danych do zapytania, pomijam' % (number, len(variants), label))
                continue
            if query in tried:
                continue
            tried.add(query)
            log.info('---\nBECKY -- proba %d/%d: %s' % (number, len(variants), label))
            log.info('Zapytanie: %s' % query)
            root = self._fetch_search_page(log, br, query, timeout)
            if abort.is_set():
                return []
            if root is None:
                continue
            candidates = []
            if variant_authors:
                strong = self._parse_search_results(log, variant_title, authors_lc, None, root, candidates)
            else:
                # Wariant bez autora w zapytaniu: autorzy pozostają „schowani”,
                # żeby wyniki zgodne z autorem nadal były premiowane
                strong = self._parse_search_results(log, variant_title, None, authors_lc, root, candidates)
            if strong:
                if authors_lc:
                    log.info('BECKY INFO: proba %d dala wynik zgodny z tytulem i autorem: %d kandydat(ow)' % (number, len(candidates)))
                else:
                    log.info('BECKY INFO: proba %d dala wynik zgodny z tytulem (bez autora w calibre): %d kandydat(ow)' % (number, len(candidates)))
                return candidates
            if candidates and not weak:
                weak = candidates
                log.info('BECKY INFO: proba %d dala tylko slabe dopasowania (%d) - zapamietuje jako rezerwe' % (number, len(candidates)))
        if weak:
            log.info('BECKY INFO: zaden wariant nie dal wyniku zgodnego z autorem; zostaja slabe dopasowania z rezerwy')
        else:
            debug_print("LubimyCzytac:: LAST")
            log.error('LAST')
        return weak

    def _surname(self, author):
        """
        Nazwisko do porównań: przy zapisie z przecinkiem – człon przed
        przecinkiem, inaczej ostatni człon (po zamianie kropek na odstępy,
        żeby inicjały nie sklejały się z nazwiskiem). Zwraca małe litery;
        pusty napis, gdy nazwisko ma mniej niż 3 znaki.
        """
        if not author:
            return ''
        if ',' in author:
            part = author.split(',')[0]
        else:
            parts = author.replace('.', ' ').split()
            part = parts[-1] if parts else ''
        part = part.strip().lower()
        return part if len(part) >= 3 else ''

    def _authors_agree(self, lc_authors, user_authors):
        """
        Czy autorzy z wyniku LC zgadzają się z autorami z calibre. Najpierw
        dotychczasowa reguła (pełna nazwa z LC zawiera się w nazwie z calibre),
        a gdy zawiedzie – zgodność samego nazwiska jako całego słowa. Dzięki
        temu „J.R.R. Tolkien” i „J. R. R. Tolkien” (tak zapisuje calibre)
        są uznawane za tego samego autora. Obie listy powinny być już
        sprowadzone do małych liter.
        """
        if not lc_authors or not user_authors:
            return False
        if self.contains(lc_authors, user_authors):
            return True
        for ua in user_authors:
            surname = self._surname(ua)
            if not surname:
                continue
            pattern = r'(?<!\w)' + re.escape(surname) + r'(?!\w)'
            for la in lc_authors:
                if re.search(pattern, la, re.UNICODE):
                    return True
        return False

    def _normalize_title(self, title):
        """
        Sprowadza tytuł do postaci porównywalnej: bez diakrytyków, małe litery,
        bez przecinków, kropek, dwukropków, średników, dywizów i pytajników,
        bez zer wiodących w liczbach („#04” → „#4”, „Tom 01” → „Tom 1”)
        i z pojedynczymi odstępami. Tą samą funkcją normalizujemy tytuł
        z calibre i tytuły z kafelków LC, więc porównanie jest symetryczne.
        """
        if not title:
            return ''
        title = get_udc().decode(title).lower()
        for ch in (',', '.', ':', ';', '-', '?'):
            title = title.replace(ch, '')
        title = re.sub(r'\b0+(?=\d)', '', title)
        return re.sub(r'\s+', ' ', title).strip()

    def _is_collective_title(self, title):
        """
        ``True`` dla tytułów wydań zbiorczych: LC wypisuje w nich kilka
        utworów po średniku („Król afer; Ostatni sędzia; Wielki gracz”) albo
        zaczyna tytuł od „KSIĄŻKI WYBRANE:”. Taki tytuł zawiera tytuł szukanej
        książki jako fragment, więc bez tego rozpoznania pakiet uchodziłby za
        wynik mocny i – przy „Fast matching” – kończył wyszukiwanie.
        """
        if not title:
            return False
        t = get_udc().decode(title).lower().strip()
        return ';' in t or t.startswith('ksiazki wybrane')

    def _parse_search_results(self, log, orig_title, orig_authors, hiddenauthors, root, matches):
        """
        Analizuje stronę wyników wyszukiwarki LC i wpisuje do listy ``matches``
        adresy książek pasujących do zapytania. Zwraca ``True``, gdy znaleziono
        wynik „mocny” (zgodny z tytułem i autorem) – ``_search`` kończy wtedy
        kolejne próby.

        Każdy wynik (kafelek ``book-card``) porównujemy z zapytaniem po
        znormalizowaniu tytułów (``_normalize_title``) i autorów (bez
        diakrytyków, małe litery). Kandydaci trafiają do czterech klas,
        w kolejności z listy LC:

        * **dokładny tytuł i autor** – tytuł identyczny po normalizacji;
        * **częściowy tytuł i autor** – tytuł z calibre jest fragmentem tytułu
          LC albo odwrotnie (np. „Hobbit” i „Hobbit, czyli tam i z powrotem”);
          tu trafia też zgodność „odwrotna” (autor w polu tytułu i tytuł w polu
          autora – zdarza się w LC; eksperymentalne);
        * **tylko tytuł** – kandydat słaby; tu lądują także wydania zbiorcze
          (``_is_collective_title``), które zawierają szukany tytuł jedynie
          jako jeden z kilku utworów;
        * **tylko autor** – kandydat słaby o najniższym priorytecie.

        Autor zgodny to autor z zapytania albo autor „schowany” (wariant
        zapytania bez autora). Gdy użytkownik nie podał autorów, zgodny tytuł
        to wszystko, co możemy sprawdzić, więc liczy się jak wynik mocny.

        Dokładny tytuł ma pierwszeństwo przed częściowym niezależnie od
        kolejności na stronie LC: dla „Cała prawda o planecie Ksi” LC zwraca
        najpierw zbiór „Cała prawda o planecie Ksi. Drugie spojrzenie…”,
        a dopiero potem właściwą książkę. Przy włączonym „Fast matching”
        jedynym kandydatem zostaje pierwszy dokładny wynik mocny (albo pierwszy
        częściowy, gdy dokładnego nie ma); bez niego lista to kolejno: dokładne,
        częściowe, słabe – do limitu „Maximum title/author search matches”.

        Wyniki niezgodne ani z tytułem, ani z autorem są odrzucane. Do wersji
        2.4.0 trafiały na listę zapasową i wracały do calibre, gdy nic innego
        nie pasowało – w praktyce były to przypadkowe książki.

        :param orig_title: szukany tytuł (wariant użyty w zapytaniu, bez diakrytyków)
        :param orig_authors: autorzy w konwencji LC, gdy byli w zapytaniu (inaczej ``None``)
        :param hiddenauthors: autorzy w konwencji LC przy zapytaniu bez autora (inaczej ``None``)
        :param root: sparsowane drzewo HTML strony wyników
        :param matches: lista wyjściowa – adresy kandydatów (zastępowana w miejscu)
        """

        # Dokładne dopasowanie tokenu klasy: contains(@class,"book-card") łapałoby
        # także elementy wewnętrzne kafelka (book-card__content, book-card__text...)
        results = root.xpath('//div[@id="ksiazki"]//div[contains(concat(" ", normalize-space(@class), " "), " book-card ")]')
        if not results:
            return False

        from . import config as cfg

        fast_match = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.FAST_MATCH, cfg.DEFAULT_STORE_VALUES[cfg.FAST_MATCH])
        max_results = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.KEY_MAX_DOWNLOADS, cfg.DEFAULT_STORE_VALUES[cfg.KEY_MAX_DOWNLOADS])

        no_author_info = not orig_authors and not hiddenauthors

        if orig_authors is not None:
            orig_authors = [lower(a) for a in orig_authors]
        if hiddenauthors is not None:
            hiddenauthors = [lower(a) for a in hiddenauthors]
        orig_title = self._normalize_title(orig_title)

        # Klasy kandydatów (adresy w kolejności z listy LC, bez powtórzeń)
        exact_strong = []
        partial_strong = []
        weak_title = []
        weak_author = []

        def add(bucket, book_url):
            if book_url not in bucket:
                bucket.append(book_url)

        i = 0
        for result in results:
            i = i + 1

            title = result.xpath(
                './/a[contains(@class,"book-card__title")]/text()'
            )
            book_url = result.xpath(
                './/a[contains(@class,"book-card__title")]/@href'
            )
            authors = result.xpath(
                './/div[contains(@class,"book-card__author")]//a/text()'
            )

            if not title or not book_url or not authors:
                continue
            raw_title = title[0]
            book_url = LubimyCzytac.BASE_URL + book_url[0]

            # Normalizujemy autorów z wyniku (bez diakrytyków, małe litery)
            authors = [lower(get_udc().decode(a)) for a in authors]
            title = self._normalize_title(raw_title)

            title_ok = bool(self.match(title, orig_title))
            exact = title_ok and title == orig_title
            collective = title_ok and not exact and self._is_collective_title(raw_title)
            author_ok = self._authors_agree(authors, orig_authors)
            hidden_ok = self._authors_agree(authors, hiddenauthors)
            inverse_ok = bool(orig_authors) and bool(self.match(authors[0], orig_title)) and bool(self.match(title, orig_authors[0]))

            log.info('''[%s] Original title: %s,
    Title: %s,
    Original authors: %s,
    Hidden authors: %s,
    Authors:%s,
    Book url: %s
    title_ok=%s exact=%s collective=%s author_ok=%s hidden_ok=%s inverse_ok=%s'''
    % (i, orig_title, title, orig_authors, hiddenauthors, authors, book_url,
       title_ok, exact, collective, author_ok, hidden_ok, inverse_ok))

            if title_ok and (author_ok or hidden_ok or no_author_info):
                if author_ok:
                    why = 'authors'
                elif hidden_ok:
                    why = 'hidden authors'
                else:
                    why = 'title only (no authors in calibre)'
                if collective:
                    add(weak_title, book_url)
                    log.info('BECKY INFO: [%s] wydanie zbiorcze zawierajace szukany tytul - tylko slaby kandydat' % (i))
                elif exact:
                    add(exact_strong, book_url)
                    log.info('BECKY INFO: [%s] matches title and %s (dokladny tytul)' % (i, why))
                else:
                    add(partial_strong, book_url)
                    log.info('BECKY INFO: [%s] matches title and %s (czesciowo)' % (i, why))
                continue

            if inverse_ok:
                add(partial_strong, book_url)
                log.info('BECKY INFO: Jest zgodnosc odwrotna!')
                log.info('BECKY INFO: [%s] matches inverse title and authors' % (i))
                continue

            if title_ok:
                add(weak_title, book_url)
                log.info('BECKY INFO: [%s] matches title (w przyblizeniu)' % (i))
                continue

            if author_ok:
                add(weak_author, book_url)
                log.info('BECKY INFO: [%s] matches authors' % (i))
                continue

            log.info('BECKY INFO: [%s] no matches - odrzucony' % (i))

        strong = bool(exact_strong or partial_strong)
        if strong and fast_match and not no_author_info:
            # „Fast matching”: zostaje jeden kandydat – pierwszy dokładny,
            # a gdy dokładnego nie ma, pierwszy częściowy
            chosen = (exact_strong or partial_strong)[:1]
            log.info('BECKY INFO: fast match - zostaje %s' % chosen[0])
        else:
            chosen = []
            for bucket in (exact_strong, partial_strong, weak_title, weak_author):
                for book_url in bucket:
                    if book_url not in chosen:
                        chosen.append(book_url)
            if len(chosen) > max_results:
                log.info('BECKY INFO: %d kandydatow, limit %d - reszta odrzucona' % (len(chosen), max_results))
                chosen = chosen[:max_results]

        del matches[:]
        matches.extend(chosen)
        return strong

    def match(self, item1, item2):
        """
        Przybliżone porównanie dwóch napisów (tytułów lub autorów).
        ``True``, gdy są identyczne albo gdy krótszy z nich występuje
        w dłuższym jako całe słowo/słowa (granice sprawdzane znakami
        innymi niż litery i cyfry, z obsługą unicode).

        Zwraca ``False`` dla pustego ``item2`` oraz ``None`` (wartość fałszywa),
        gdy któryś z argumentów nie jest napisem.
        """
        if not item2:
            return False
        if isinstance(item1, unicode) and isinstance(item2, unicode):
            if item1 == item2:
                return True
            shorter, longer = (item1, item2) if len(item1) <= len(item2) else (item2, item1)
            if not shorter:
                return False
            pattern = r'(?<!\w)' + re.escape(shorter) + r'(?!\w)'
            return re.search(pattern, longer, re.UNICODE) is not None

    def contains(self, list1, list2):
        """
        ``True``, gdy którykolwiek element ``list1`` jest podciągiem
        któregokolwiek elementu ``list2``. Operacja celowo jednokierunkowa:
        ``contains(['Shelby'], ['Shelby Mahurin'])`` jest prawdą, odwrotnie – nie.
        Puste lub ``None`` listy dają ``False``.
        """
        if not list1 or not list2:
            return False
        for el in list1:
            if any(el in s for s in list2):
                return True
        return False

    def replaceInList(self, arr, find, replace):
        """Zamienia w miejscu wszystkie wystąpienia ``find`` na ``replace`` w liście ``arr``."""
        base=0
        for cnt in range(arr.count(find)):
            offset=arr.index(find, base)
            arr[offset]=replace
            base=offset+1
        return arr

    def download_cover(self, log, result_queue, abort,
            title=None, authors=None, identifiers={}, timeout=30):
        """
        Pobiera okładkę (wymagane przez calibre dla ``capabilities`` z ``cover``).

        Adres okładki bierzemy z pamięci podręcznej wypełnianej podczas
        ``identify``. Jeśli go tam nie ma (np. użytkownik pobiera samą okładkę),
        uruchamiamy ``identify`` na własnej kolejce i bierzemy okładkę
        najtrafniejszego wyniku. Pobrane bajty obrazka trafiają do
        ``result_queue`` jako krotka ``(self, dane)``.
        """
        cached_url = self.get_cached_cover_url(identifiers)
        if cached_url is None:
            log.info('No cached cover found, running identify')
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors,
                    identifiers=identifiers)
            if abort.is_set():
                return
            results = []
            while True:
                try:
                    results.append(rq.get_nowait())
                except Empty:
                    break
            results.sort(key=self.identify_results_keygen(
                title=title, authors=authors, identifiers=identifiers))
            for mi in results:
                cached_url = self.get_cached_cover_url(mi.identifiers)
                if cached_url is not None:
                    break
        if cached_url is None:
            log.info('No cover found')
            return

        if abort.is_set():
            return
        br = self.browser
        log.info('Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Failed to download cover from:', cached_url)


if __name__ == '__main__':  # testy
    # Uruchamianie:
    #     calibre-debug -e __init__.py
    # Najpierw wykonują się szybkie testy jednostkowe funkcji pomocniczych
    # (bez sieci), potem testy integracyjne calibre pobierające dane z LC.
    import unittest

    class HelperTests(unittest.TestCase):
        """Testy funkcji pomocniczych – nie wymagają w pełni zainicjowanej wtyczki."""
        @classmethod
        def setUpClass(cls):
            cls.plugin = LubimyCzytac.__new__(LubimyCzytac)

        def test_match_exact_and_word_boundaries(self):
            self.assertTrue(self.plugin.match('Dune', 'Dune'))
            self.assertTrue(self.plugin.match('Dune', 'Dune Messiah'))
            self.assertFalse(self.plugin.match('Dune', 'Duneland'))
            self.assertFalse(self.plugin.match('Dune', ''))

        def test_match_unicode_and_punctuation(self):
            self.assertTrue(self.plugin.match('Łódź', 'Opowieść o Łódź'))
            self.assertTrue(self.plugin.match('08/15', '08/15. Powrót'))
            self.assertTrue(self.plugin.match("O'Brien", "O'Brien"))
            self.assertTrue(self.plugin.match('Jean-Luc', 'Jean-Luc'))

        def test_contains_substring_direction(self):
            # contains() sprawdza, czy element list1 występuje wewnątrz
            # elementu list2 – operacja jest celowo jednokierunkowa
            self.assertFalse(self.plugin.contains(['Shelby Mahurin'], ['Shelby']))
            self.assertTrue(self.plugin.contains(['Shelby'], ['Shelby Mahurin']))
            self.assertFalse(self.plugin.contains(['Shelby'], ['Mahurin']))

        def test_contains_empty_inputs(self):
            self.assertFalse(self.plugin.contains([], ['Shelby']))
            self.assertFalse(self.plugin.contains(['Shelby'], []))
            self.assertFalse(self.plugin.contains(None, ['Shelby']))

        def test_replace_all_occurrences_in_place(self):
            values = ['a', 'b', 'a', 'c', 'a']
            result = self.plugin.replaceInList(values, 'a', 'x')
            self.assertIs(result, values)
            self.assertEqual(result, ['x', 'b', 'x', 'c', 'x'])

        def test_split_title_on_dot_or_colon(self):
            self.assertEqual(self.plugin._split_title('The Naturals. Więzy krwi'), ('The Naturals', 'Więzy krwi'))
            self.assertEqual(self.plugin._split_title('The Naturals: Więzy krwi'), ('The Naturals', 'Więzy krwi'))
            self.assertEqual(self.plugin._split_title('Summoner Zaklinacz 1. Początek'), ('Summoner Zaklinacz 1', 'Początek'))
            self.assertEqual(self.plugin._split_title('Hobbit'), (None, None))
            self.assertEqual(self.plugin._split_title('Koniec.'), ('Koniec', None))
            self.assertEqual(self.plugin._split_title(''), (None, None))
            # kropka w skrócie lub inicjale nie jest separatorem
            self.assertEqual(self.plugin._split_title('Czarodziejski statek cz.1'), (None, None))
            self.assertEqual(self.plugin._split_title('Opowieści J.R.R. Tolkiena'), (None, None))
            self.assertEqual(self.plugin._split_title('Ubik Philipa K. Dicka'), (None, None))
            self.assertEqual(self.plugin._split_title('Achaja. Tom II'), ('Achaja', 'Tom II'))

        def test_normalize_title(self):
            self.assertEqual(self.plugin._normalize_title('Moje szczęśliwe małżeństwo #04'), 'moje szczesliwe malzenstwo #4')
            self.assertEqual(self.plugin._normalize_title('Pomnik Cesarzowej Achai - Tom I'), 'pomnik cesarzowej achai tom i')
            self.assertEqual(self.plugin._normalize_title('Cała prawda o planecie Ksi.'), 'cala prawda o planecie ksi')
            self.assertEqual(self.plugin._normalize_title('Czarodziejski statek cz.1'), 'czarodziejski statek cz1')
            self.assertEqual(self.plugin._normalize_title('Rok 2004'), 'rok 2004')
            self.assertEqual(self.plugin._normalize_title(''), '')
            self.assertEqual(self.plugin._normalize_title(None), '')

        def test_detect_download_mode(self):
            # symulacja: wątek główny „czeka” w funkcji o nazwie jak w calibre,
            # wtyczka sprawdza tryb z własnego wątku – dokładnie jak w procesie roboczym
            import types
            fake = types.ModuleType('calibre.ebooks.metadata.sources.worker')
            seen = {}
            def plugin_side(label):
                seen[label] = detect_download_mode()
            def identify(label):
                t = threading.Thread(target=plugin_side, args=(label,))
                t.start()
                t.join()
            src = ('def single_identify(title, authors, identifiers):\n    identify("okno")\n'
                   'def main(do_identify, covers, metadata, ensure_fields, tdir):\n    identify("masowe")\n')
            exec(compile(src, 'worker', 'exec'), fake.__dict__)
            fake.identify = identify
            fake.single_identify('t', ['a'], {})
            fake.main(True, True, {}, None, '')
            plugin_side('bezposrednio')
            self.assertEqual(seen, {'okno': 'single', 'masowe': 'bulk', 'bezposrednio': 'unknown'})

        def test_manual_search_hint(self):
            # blok __main__ działa poza pakietem, więc zamiast worker.html_escape – odpowiednik
            html_escape = lambda t: t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            html = self.plugin._manual_search_hint('Król <pozwów>', ['John Grisham'], html_escape)
            self.assertIn('https://www.google.com/search?q=site%3Alubimyczytac.pl%20%22Kr%C3%B3l%20%3Cpozw%C3%B3w%3E%22%20John%20Grisham', html)
            self.assertIn('https://duckduckgo.com/?q=site%3Alubimyczytac.pl', html)
            self.assertIn('https://lubimyczytac.pl/szukaj/ksiazki?phrase=Kr%C3%B3l%20%3Cpozw%C3%B3w%3E%20John%20Grisham', html)
            self.assertIn('lubimyczytac:74063', html)
            self.assertNotIn('<pozwów>', html)      # tytuł w tekście jest zabezpieczony
            html = self.plugin._manual_search_hint('Leonia', None, html_escape)
            self.assertIn('%22Leonia%22', html)
            mi = self.plugin._manual_search_result('Leonia', None, html_escape)
            self.assertEqual((mi.title, mi.identifiers), ('Leonia', {}))
            self.assertTrue(mi.comments.startswith('<p><span style="color:red'))

        def test_collective_title(self):
            self.assertTrue(self.plugin._is_collective_title('Król afer; Ostatni sędzia; Wielki gracz'))
            self.assertTrue(self.plugin._is_collective_title('KSIĄŻKI WYBRANE: Uliczny adwokat, Ocean miłości'))
            self.assertFalse(self.plugin._is_collective_title('Igrzyska Śmierci. Trylogia'))
            self.assertFalse(self.plugin._is_collective_title('Cała prawda o planecie Ksi. Drugie spojrzenie na planetę Ksi'))
            self.assertFalse(self.plugin._is_collective_title(''))

        def test_query_variants_order(self):
            labels = [v[0] for v in self.plugin._query_variants('Cykl. Tytul', ['X Y'])]
            self.assertEqual(labels, ['autor + pelny tytul', 'autor + tytul przed separatorem',
                                      'autor + tytul po separatorze', 'tylko pelny tytul',
                                      'tylko tytul przed separatorem'])
            self.assertEqual([v[0] for v in self.plugin._query_variants('Tytul', None)], ['tylko pelny tytul'])
            # tytuł z kropką w inicjale: bez wariantów „przed/po separatorze”
            self.assertEqual([v[0] for v in self.plugin._query_variants('Ubik Philipa K. Dicka', ['X Y'])],
                             ['autor + pelny tytul', 'tylko pelny tytul'])

        def test_surname(self):
            self.assertEqual(self.plugin._surname('j. r. r. tolkien'), 'tolkien')
            self.assertEqual(self.plugin._surname('kowalski, jan'), 'kowalski')
            self.assertEqual(self.plugin._surname('johann wolfgang von goethe'), 'goethe')
            self.assertEqual(self.plugin._surname('li'), '')
            self.assertEqual(self.plugin._surname(''), '')

        def test_authors_agree_full_name_or_surname(self):
            self.assertTrue(self.plugin._authors_agree(['jennifer lynn barnes'], ['jennifer lynn barnes']))
            # calibre zapisuje inicjały z odstępami, LC bez – decyduje nazwisko
            self.assertTrue(self.plugin._authors_agree(['j.r.r. tolkien'], ['j. r. r. tolkien']))
            self.assertFalse(self.plugin._authors_agree(['trine angelsen'], ['jennifer lynn barnes']))
            self.assertFalse(self.plugin._authors_agree(['j.r.r. tolkien'], None))
            self.assertFalse(self.plugin._authors_agree([], ['tolkien']))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HelperTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)

    from calibre.ebooks.metadata.sources.test import (test_identify_plugin, title_test, authors_test)

    # Testy integracyjne: każdy przypadek to (dane wejściowe, lista sprawdzeń)
    lctests = [
        (
          {
             'identifiers':{'lubimyczytac': '4965040'},
             'title':'Krew i miód',
             'authors':['Shelby Mahurin']
          },
          [
             title_test('Krew i miód'),
             authors_test(['Shelby Mahurin']),
          ]
        ),
        (
          {
             'identifiers':{'lubimyczytac': '4954343'},
             'title':'Cień utraconego świata',
             'authors':['James Islington']
          },
          [
             title_test('Cień utraconego świata'),
             authors_test(['James Islington']),
          ]
        ),

        # Dodatkowe przypadki z pakietu 50 rekordów JSON-LD (46 książek).
        # Dwa rekordy audiobooków oraz testy wymagające osobnej weryfikacji
        # typu zasobu pozostają poza test_identify_plugin.
        (
          {
             'identifiers':{'lubimyczytac': '172417'},
             'title':'"Mein Kampf". Biografia książki',
             'authors':['Antoine Vitkine']
          },
          [
             title_test('„Mein Kampf”. Biografia książki'),
             authors_test(['Antoine Vitkine']),
          ]
        ),
        (
          {
             'identifiers':{'lubimyczytac': '4898567'},
             'title':'Arthur & George',
             'authors':['Julian Barnes'],
          },
          [
             title_test('Arthur & George'),
             authors_test(['Julian Barnes']),
          ]
        ),
        (
          {
             'identifiers':{'lubimyczytac': '4821058'},
             'title':'Hobbit',
             'authors':['J.R.R. Tolkien']
          },
          [
             title_test('Hobbit'),
             authors_test(['J. R. R. Tolkien']),
          ]
        ),
        (
          {
             'identifiers':{'lubimyczytac': '4866052'},
             'title':'Ostatni. Prawdziwa historia żołnierza warszawskiej mafii',
             'authors':['Marzena Matuszak']
          },
          [
             title_test('Ostatni. Prawdziwa historia żołnierza warszawskiej mafii'),
             authors_test(['Marzena Matuszak'], subset=True),
          ]
        ),

        # Przypadki przez wyszukiwarkę (bez identyfikatora LC) – od 2.4.1:
        # dokładny tytuł ma pierwszeństwo przed zbiorem „…Drugie spojrzenie…”,
        # a zero wiodące w numerze tomu („#04” vs „#4” na LC) nie psuje dopasowania.
        (
          {
             'title':'Cała prawda o planecie Ksi',
             'authors':['Janusz A. Zajdel']
          },
          [
             title_test('Cała prawda o planecie Ksi', exact=True),
             authors_test(['Janusz A. Zajdel']),
          ]
        ),
        (
          {
             'title':'Moje szczęśliwe małżeństwo #04',
             'authors':['Akumi Agitogi']
          },
          [
             title_test('Moje szczęśliwe małżeństwo #4', exact=True),
             authors_test(['Akumi Agitogi'], subset=True),
          ]
        ),
    ]

    def do_test(lctests, start=0, stop=None):
        """Uruchamia wybrany zakres przypadków z ``lctests`` (domyślnie wszystkie)."""
        if stop is None:
            stop = len(lctests)
        lctests = lctests[start:stop]
        test_identify_plugin(LubimyCzytac.name, lctests, fail_missing_meta=False)

    do_test(lctests)
