#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
"""
Wątek roboczy wtyczki LubimyCzytać: pobiera i parsuje stronę pojedynczej książki.

Dla każdego kandydata znalezionego w ``LubimyCzytac.identify`` (``__init__.py``)
tworzony jest jeden obiekt ``Worker``. Pobiera on stronę książki, wyciąga z niej
metadane (tytuł, autorów, serię, ISBN, ocenę, opis, okładkę itd.), składa obiekt
``calibre.ebooks.metadata.book.base.Metadata`` i wkłada go do kolejki wyników.

Źródła danych na stronie LC – w kolejności od najbardziej do najmniej stabilnego:

1. JSON-LD (``<script type="application/ld+json">``, obiekt ``Book``/``Audiobook``),
2. znaczniki ``<meta property="books:...">`` i Open Graph (``og:...``),
3. zwykły HTML (XPath) – najczęściej zmieniany przez serwis.

Większość parserów próbuje kolejno kilku źródeł. Każda próba może zostać
odnotowana przez ``record_parse_attempt`` i wypisana w raporcie diagnostycznym
(patrz ``BECKYDEBUG`` – włączany zmienną środowiskową ``LUBIMYCZYTAC_DEBUG=1``).

Komunikaty w logu celowo nie zawierają polskich znaków diakrytycznych
(``strip_accents``) – użytkownicy wklejają logi na forum MobileRead, gdzie
kodowanie bywało problemem.
"""
from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Roman Cupisz <roman.cupisz+calibre@gmail.com>, 2015-2026 enhancements by Becky <becky@fr.pl>'
__docformat__ = 'restructuredtext en'

from six import text_type as unicode

import os
import socket
import time
import re
import datetime
import json
from threading import Thread

from lxml.html import fromstring
from lxml.html import tostring

from calibre.ebooks.metadata.book.base import Metadata
from calibre.library.comments import sanitize_comments_html
from calibre.utils.cleantext import clean_ascii_chars
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import fixauthors

from mechanize import HTTPError

try:
    from html import unescape as html_unescape        # Python 3
except ImportError:
    from HTMLParser import HTMLParser                   # Python 2 (calibre 3.48)
    html_unescape = HTMLParser().unescape

from . import config as cfg

# Formy wyrazu „strona” do odmiany liczby stron w komentarzu: 1 strona,
# 2–4 strony, 5+ stron (patrz funkcja odmiana())
frazastrona = ["strona", "strony", "stron"]

# Flaga diagnostyki parserów (niezależna od calibre.constants.DEBUG).
# Gdy włączona, na końcu pracy każdego Workera do logu trafia raport
# z wynikami wszystkich prób parsowania (log_parse_diagnostics).
# Domyślnie wyłączona; włącza ją zmienna środowiskowa LUBIMYCZYTAC_DEBUG
# (wartość 1/true/yes/tak), bez edycji kodu – także u użytkownika zgłaszającego problem:
#   Windows:     set LUBIMYCZYTAC_DEBUG=1 && calibre-debug -g
#   Linux/macOS: LUBIMYCZYTAC_DEBUG=1 calibre-debug -g
# Zmienną trzeba ustawić przed uruchomieniem calibre (odczyt przy imporcie modułu).
BECKYDEBUG = os.environ.get('LUBIMYCZYTAC_DEBUG', '').strip().lower() in ('1', 'true', 'yes', 'tak')

# Limity skanowania wydań przy opcji „Prefer matching ISBN”. Lista wydań nie
# zawiera ISBN, więc każde wydanie wymaga pobrania osobnej strony (ok. 400 KB).
# „Pan Tadeusz” ma 108 wydań – bez limitu jedno pobranie metadanych potrafiło
# trwać kwadrans, a calibre kończyło zadanie bez pokazania logu.
ISBN_SCAN_MAX_EDITIONS = 20   # najwyżej tyle stron wydań
ISBN_SCAN_MAX_SECONDS = 60    # i nie dłużej niż tyle sekund łącznie


class Worker(Thread):

    """
    Pobiera szczegóły książki ze strony LubimyCzytac.pl w osobnym wątku.

    Cykl życia: ``identify`` tworzy Workera z adresem kandydata, uruchamia go
    (``start``) i czeka na zakończenie. ``run`` → ``get_details`` (pobranie
    strony, ewentualny wybór wydania po ISBN) → ``parse_details`` (parsowanie
    i złożenie ``Metadata``) → ``result_queue.put(mi)``.
    """

    def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20, target_isbn=None):
        """
        :param url: adres strony książki w LC
        :param result_queue: kolejka, do której trafi gotowy obiekt ``Metadata``
        :param browser: przeglądarka calibre (``mechanize``); klonujemy ją, bo
            każdy wątek potrzebuje własnej instancji
        :param log: log calibre
        :param relevance: pozycja kandydata na liście z ``identify`` – zapisywana
            jako ``mi.source_relevance`` (ostatnie kryterium sortowania wyników)
        :param plugin: instancja wtyczki (dostęp do pamięci podręcznej okładek/ISBN)
        :param timeout: limit czasu pojedynczego żądania HTTP (s)
        :param target_isbn: ISBN z calibre, gdy włączona jest opcja
            „Prefer matching ISBN” – wtedy szukamy wydania o tym numerze
        """
        Thread.__init__(self)
        self.daemon = True
        self.url, self.result_queue = url, result_queue
        self.log, self.timeout = log, timeout
        self.relevance, self.plugin = relevance, plugin
        self.target_isbn = target_isbn
        self.browser = browser.clone_browser()
        self.cover_url = self.lubimy_czytac_id = self.isbn = None
        # Tytuły innych wydań odczytane w parse_inne_wydania_all(),
        # wykorzystywane ponownie przez parse_inne_wydania_short()
        self.inne_wydania_tytuly_short = None
        # Strona pełnej listy wydań pobierana najwyżej raz na Workera
        # (korzystają z niej skan ISBN i listy wydań w komentarzu)
        self._editions_root = None
        self._editions_checked = False
        # Szczegółowy rejestr prób parserów, wykorzystywany w diagnostyce
        self.parse_diagnostics = []
        self._diagnostic_attempts = {}

    def run(self):
        """Punkt wejścia wątku – każdy nieobsłużony wyjątek trafia do logu, a nie do calibre."""
        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r'%self.url)

    def _diagnostic_value(self, value):
        """Skraca i normalizuje wartość na potrzeby raportu diagnostycznego (max 240 znaków)."""
        if value is None or value == '' or value == []:
            return 'Brak'
        try:
            text = unicode(value)
        except Exception:
            text = repr(value)
        text = ' '.join(text.split())
        if len(text) > 240:
            text = text[:237] + '...'
        return text

    def record_parse_attempt(self, field, source, value, error=None):
        """
        Zapisuje wynik pojedynczej próby pobrania pola.

        :param field: nazwa pola (np. ``isbn``, ``series``)
        :param source: źródło danych; dla ``'XPath'`` dopisywany jest numer kolejnej próby
        :param value: odczytana wartość (``None``, gdy nic nie znaleziono)
        :param error: wyjątek, jeśli próba zakończyła się błędem
        """
        attempt = self._diagnostic_attempts.get(field, 0) + 1
        self._diagnostic_attempts[field] = attempt
        if source == 'XPath':
            source = 'XPath proba #%d' % attempt
        self.parse_diagnostics.append({
            'field': field,
            'source': source,
            'value': self._diagnostic_value(value),
            'error': unicode(error) if error else None,
        })

    def log_parse_diagnostics(self):
        """Wypisuje do logu raport ze wszystkich prób parsowania (tylko gdy ``BECKYDEBUG`` jest włączone)."""
        if not BECKYDEBUG:
            return
        self.log.info('BECKYDEBUG: aktywny; worker=%s; zarejestrowanych prob=%d' %
                      (__file__, len(self.parse_diagnostics)))
        if not self.parse_diagnostics:
            self.log.info('BECKYDEBUG: brak zarejestrowanych prob parse_first()')
            return
        self.log.info('--- RAPORT DIAGNOSTYCZNY PARSOWANIA LC ---')
        current_field = None
        for item in self.parse_diagnostics:
            if item['field'] != current_field:
                current_field = item['field']
                self.log.info('[%s]' % current_field)
            line = '  %s: %s' % (item['source'], item['value'])
            if item['error']:
                line += ' (wyjatek: %s)' % item['error']
            self.log.info(line)
        self.log.info('--- KONIEC RAPORTU DIAGNOSTYCZNEGO ---')

    def parse_first(self, root, xpath, loginfo, convert=lambda x: x[0].strip()):
        """
        Wykonuje XPath i zwraca pierwszy wynik przekształcony funkcją ``convert``
        (domyślnie: pierwszy węzeł jako tekst bez białych znaków na końcach).
        Zwraca ``None``, gdy nic nie znaleziono lub wystąpił błąd; każdą próbę
        odnotowuje w rejestrze diagnostycznym.

        :param loginfo: nazwa pola do logu i raportu diagnostycznego
        """
        try:
            nodes = root.xpath(xpath)
            if nodes:
                value = convert(nodes)
                nodes_temp = strip_accents(unicode(str(value)))
                self.log.info('BECKY INFO: Found %s: %s' % (loginfo,nodes_temp))
                self.record_parse_attempt(loginfo, 'XPath', value)
                return value
            self.record_parse_attempt(loginfo, 'XPath', None)
            return None
        except Exception as e:
            self.record_parse_attempt(loginfo, 'XPath', None, e)
            self.log.exception('Error parsing for %s with xpath: %s' % (loginfo, xpath))

    def get_details(self):
        """
        Pobiera stronę książki i przekazuje ją do ``parse_details``.

        Obsługa błędów HTTP:

        * 500 – LC zwraca ten kod dla niektórych stron, które mimo to zawierają
          komplet danych, dlatego próbujemy parsować treść odpowiedzi;
        * 404 / 503 / timeout – kończymy pracę z komunikatem w logu.

        Gdy ustawiono ``target_isbn``, przed parsowaniem sprawdzamy inne wydania
        książki i – jeśli któreś ma identyczny ISBN – parsujemy właśnie je.
        """
        try:
            self.log.info('LubimyCzytac.pl   url: %r'%self.url)
            response = self.browser.open_novisit(self.url, timeout=self.timeout)
            raw = response.read().strip()
        except HTTPError as e:
            self.log.error('HTTP Error: %s' % e)
            if e.code == 500:
                self.log.error('Serwis LubimyCzytac domyślnie zwraca blad 500.')
                self.log.error('To nie jest problem zwiazany z wtyczka!')
                # Pobieramy zawartość odpowiedzi, nawet jeśli wystąpił błąd 500
                raw = e.read().strip()
                self.log.info("Probuje parsowac strone pomimo bledu 500")
            else:
                self.log.error("Inny blad HTTP, nie mozna pobrac danych")
                return
        except Exception as e:
            if callable(getattr(e, 'getcode', None)) and \
                    e.getcode() == 404:
                self.log.error('URL malformed: %r'%self.url)
                return
            if callable(getattr(e, 'getcode', None)) and \
                    e.getcode() == 503:
                self.log.error('Serwis LubimyCzytac jest niedostepny.')
                self.log.error('To nie jest problem zwiazany z wtyczka!')
                return
            if callable(getattr(e, 'getcode', None)) and \
                    e.getcode() == 500:
                self.log.error('Serwis LubimyCzytac domyślnie zwraca blad 500.')
                self.log.error('To nie jest problem zwiazany z wtyczka!')
                return
            attr = getattr(e, 'args', [None])
            attr = attr if attr else [None]
            if isinstance(attr[0], socket.timeout):
                msg = 'LubimyCzytac.pl timed out. Try again later.'
                self.log.error(msg)
            else:
                msg = 'Failed to make details query: %r'%self.url
                self.log.exception(msg)
            return

        raw = raw.decode('utf-8', errors='replace')

        if 'Przepraszamy, nie możemy znaleźć strony, której szukasz.' in raw:
            self.log.error('URL malformed: %r'%self.url)
            return

        try:
            root = fromstring(clean_ascii_chars(raw.encode("utf-8")))
        except:
            msg = 'Failed to parse LubimyCzytac.pl details page: %r'%self.url
            self.log.exception(msg)
            return

        if self.target_isbn:
            try:
                matched = self.find_edition_by_isbn(root)
                if matched:
                    self.url, root = matched
                    self.log.info('ISBN-EDITION: WYBRANO WYDANIE ZGODNE Z ISBN: %s' % self.url)
            except Exception:
                # Nie przerywamy identyfikacji: w razie błędu pozostaje pierwotny wynik
                self.log.exception('ISBN-EDITION: sprawdzanie innych wydan nie powiodlo sie; pozostaje pierwotny wynik')

        self.parse_details(root)

    def _normalize_isbn(self, value):
        """Sprowadza ISBN do samych cyfr (i ``X``) wielkimi literami, żeby dało się go porównać; ``None`` dla pustego."""
        if not value:
            return None
        value = re.sub(r'[^0-9Xx]', '', unicode(value)).upper()
        return value or None

    def _isbn_from_root(self, root):
        """Odczytuje ISBN ze strony książki: najpierw ``<meta books:isbn>``, potem sekcja szczegółów."""
        values = root.xpath('//meta[@property="books:isbn"]/@content')
        if not values:
            values = root.xpath('//div[@id="book-details"]//dt[contains(text(),"ISBN:")]/following-sibling::dd[1]//text()')
        return self._normalize_isbn(' '.join(values).strip() if values else None)

    def has_other_editions(self, root):
        """
        Czy strona książki pokazuje inne wydania: przycisk „Inne wydania”
        (``#buttonShowOtherEditions``), blok ``#other-editions`` albo link do
        ``/ksiazka/wydania/``. Gdy ich nie ma, książka ma jedno wydanie
        i pobieranie listy wydań byłoby zbędnym żądaniem.
        """
        return bool(root.xpath('//button[@id="buttonShowOtherEditions"] | //div[@id="other-editions"] '
                               '| //a[contains(@href, "/ksiazka/wydania/")]'))

    def editions_list_url(self, root):
        """
        Adres pełnej listy wydań: z linku „więcej” na stronie książki (ma właściwy
        slug), a gdy go nie ma – zbudowany z adresu książki. ``None`` dla adresu
        niebędącego stroną książki.
        """
        hrefs = root.xpath('//a[contains(@href, "/ksiazka/wydania/")]/@href')
        if hrefs:
            href = hrefs[0]
            return href if href.startswith('http') else 'https://lubimyczytac.pl' + href
        match = re.search(r'/ksiazka/(\d+)(?:/([^/?#]+))?', self.url)
        if not match:
            return None
        url = 'https://lubimyczytac.pl/ksiazka/wydania/' + match.group(1)
        if match.group(2):
            url += '/' + match.group(2)
        return url

    def fetch_editions_root(self, root):
        """
        Pobiera stronę pełnej listy wydań – najwyżej raz na Workera – i zwraca
        jej drzewo HTML. ``None``, gdy strona książki nie pokazuje innych wydań
        (bez żądania) albo pobranie się nie powiodło.
        """
        if self._editions_checked:
            return self._editions_root
        self._editions_checked = True
        if not self.has_other_editions(root):
            self.log.info('BECKY INFO: strona ksiazki nie pokazuje innych wydan - pomijam pobieranie listy wydan')
            return None
        editions_url = self.editions_list_url(root)
        if not editions_url:
            return None
        try:
            response = self.browser.open_novisit(editions_url, timeout=self.timeout)
            raw = response.read().strip()
            if not isinstance(raw, unicode):
                raw = raw.decode('utf-8', errors='replace')
            self._editions_root = fromstring(clean_ascii_chars(raw.encode('utf-8')))
            self.log.info('BECKY INFO: Pobrano strone pelnej listy wydan: %s' % editions_url)
        except Exception as e:
            self.log.warning('BECKY INFO: Nie udalo sie pobrac pelnej listy wydan: %s' % e)
        return self._editions_root

    def edition_links(self, editions_root):
        """Lista ``(adres, tytuł)`` z pełnej listy wydań, bez powtórzeń, w kolejności LC."""
        links = []
        seen = set()
        if editions_root is None:
            return links
        for node in editions_root.xpath(
                '//div[@id="editionsList"]//a[contains(concat(" ", normalize-space(@class), " "), " book-card__title ")]'):
            href = node.get('href')
            title = normalize_edition_title(''.join(node.itertext()))
            if not href or not title:
                continue
            if href.startswith('/'):
                href = 'https://lubimyczytac.pl' + href
            if href not in seen:
                seen.add(href)
                links.append((href, title))
        return links

    def find_edition_by_isbn(self, root):
        """
        Znajduje wydanie książki o ISBN zgodnym z ISBN z calibre (opcja
        „Prefer matching ISBN”).

        Lista wydań nie zawiera numerów ISBN, więc trzeba pobierać strony
        kolejnych wydań – aż do pierwszej dokładnej zgodności. Żeby nie
        zamieniało się to w kwadrans przy książkach o stu wydaniach:

        * strona listy jest pobierana tylko wtedy, gdy strona książki pokazuje
          inne wydania (``fetch_editions_root``), i tylko raz na Workera;
        * pomijamy audiobooki i pierwotnego kandydata;
        * najpierw sprawdzamy wydania o tym samym tytule co pierwotny kandydat
          (wydanie użytkownika rzadko ma inny tytuł niż to, które pasowało
          do calibre), potem pozostałe;
        * skan kończy się po ``ISBN_SCAN_MAX_EDITIONS`` stronach albo po
          ``ISBN_SCAN_MAX_SECONDS`` sekundach – wtedy pozostaje pierwotny wynik,
          a w logu jest informacja, ile wydań nie zostało sprawdzonych.

        Zwraca krotkę ``(url, root)`` zgodnego wydania albo ``None``.
        """
        target = self._normalize_isbn(self.target_isbn)
        if not target:
            return None
        self.log.info('ISBN-EDITION: ISBN z Calibre: %s' % target)

        # Jeśli pierwotny wynik już ma właściwy ISBN, nie wykonujemy dodatkowych żądań
        current_isbn = self._isbn_from_root(root)
        if current_isbn == target:
            self.log.info('ISBN-EDITION: pierwotny wynik ma zgodny ISBN; pomijam szczegolowe sprawdzanie innych wydan')
            return None

        editions_root = self.fetch_editions_root(root)
        if editions_root is None:
            self.log.info('ISBN-EDITION: brak listy wydan; pozostaje pierwotne wydanie')
            return None

        candidates = []
        for href, title in self.edition_links(editions_root):
            # Wydanie ma być książką, nie audiobookiem
            if '/ksiazka/' not in href:
                self.log.info('ISBN-EDITION: pomijam nie-ksiazkowa pozycje: %s' % href)
                continue
            # Nie pobieramy ponownie strony pierwotnego kandydata
            if href.rstrip('/') == self.url.rstrip('/'):
                continue
            candidates.append((href, title))
        self.log.info('ISBN-EDITION: liczba wydan do sprawdzenia: %d' % len(candidates))

        # Najpierw wydania o tytule identycznym z tytułem pierwotnego kandydata
        try:
            main_title = strip_accents(normalize_edition_title(self.parse_title(root))).lower()
        except Exception:
            main_title = ''
        if main_title:
            same = [c for c in candidates if strip_accents(c[1]).lower() == main_title]
            other = [c for c in candidates if strip_accents(c[1]).lower() != main_title]
            candidates = same + other

        started = time.time()
        checked = 0
        for href, title in candidates:
            if checked >= ISBN_SCAN_MAX_EDITIONS:
                self.log.info('ISBN-EDITION: limit %d stron wydan osiagniety; %d wydan nie sprawdzono'
                              % (ISBN_SCAN_MAX_EDITIONS, len(candidates) - checked))
                break
            if time.time() - started > ISBN_SCAN_MAX_SECONDS:
                self.log.info('ISBN-EDITION: limit czasu %d s osiagniety po %d stronach; %d wydan nie sprawdzono'
                              % (ISBN_SCAN_MAX_SECONDS, checked, len(candidates) - checked))
                break
            checked += 1
            try:
                detail_response = self.browser.open_novisit(href, timeout=self.timeout)
                detail_raw = detail_response.read().strip()
                if not isinstance(detail_raw, unicode):
                    detail_raw = detail_raw.decode('utf-8', errors='replace')
                detail_root = fromstring(clean_ascii_chars(detail_raw.encode('utf-8')))
                isbn = self._isbn_from_root(detail_root)
                self.log.info('ISBN-EDITION: %s | ISBN=%s | %s' % (title, isbn or 'BRAK', href))
                if isbn == target:
                    self.log.info('ISBN-EDITION: DOKLADNA ZGODNOSC: %s | %s' % (target, href))
                    # Natychmiast kończymy: dalsze strony wydań nie są już potrzebne
                    return href, detail_root
            except Exception as e:
                self.log.info('ISBN-EDITION: nie udalo sie odczytac %s: %s' % (href, e))
        self.log.info('ISBN-EDITION: brak zgodnego ISBN; pozostaje pierwotne wydanie')
        return None

    def parse_details(self, root):
        """
        Parsuje stronę książki i składa obiekt ``Metadata``.

        Kolejność działań:

        1. odczyt ustawień wtyczki (które informacje dołączać do komentarza);
        2. pola obowiązkowe: ID LC, tytuł, autorzy – bez nich rezygnujemy;
        3. pola opcjonalne – każde w osobnym ``try``, aby błąd jednego parsera
           nie przepadł z całością;
        4. komentarz (opis) rozszerzany na końcu o wybrane informacje
           (liczba stron, tytuł oryginału, tłumacze, seria, kategoria, słowa
           kluczowe, ocena, liczba ocen, daty pierwszych wydań, ID), a na
           początku o informacje o innych wydaniach;
        5. zapis ISBN i adresu okładki do pamięci podręcznej wtyczki,
           ``clean_downloaded_metadata`` i wstawienie wyniku do kolejki.

        Każdy dołączany akapit ma własny atrybut ``id`` (np. ``<p id="strony">``),
        dzięki czemu inne narzędzia (np. wtyczka METAmover) mogą go łatwo odnaleźć.
        """
        self.log.info('---------------------------------  PARSOWANIE  ---------------------------------')
        append_pages = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_PAGES, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_PAGES])
        append_pages_new = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_PAGES_NEW, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_PAGES_NEW])
        append_original_title = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_ORIGINAL_TITLE, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_ORIGINAL_TITLE])
        append_translators = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_TRANSLATION, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_TRANSLATION])
        append_serwyd = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_SERWYD, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_SERWYD])
        append_kategoria = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_GENRE, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_GENRE])
        append_keywords = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_KEYWORDS, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_KEYWORDS])
        append_rating = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_RATING, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_RATING])
        append_rating_counts = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_RATING_COUNT, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_RATING_COUNT])
        append_id = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_ID, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_ID])
        before_other_editions_exist = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.BEFORE_OTHER_EDITIONS_EXIST, cfg.DEFAULT_STORE_VALUES[cfg.BEFORE_OTHER_EDITIONS_EXIST])
        before_other_editions_all = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.BEFORE_OTHER_EDITIONS_ALL, cfg.DEFAULT_STORE_VALUES[cfg.BEFORE_OTHER_EDITIONS_ALL])
        before_other_editions_short = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.BEFORE_OTHER_EDITIONS_SHORT, cfg.DEFAULT_STORE_VALUES[cfg.BEFORE_OTHER_EDITIONS_SHORT])
        before_hr = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.BEFORE_HR, cfg.DEFAULT_STORE_VALUES[cfg.BEFORE_HR])
        asTags = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.TAGS_AS, cfg.DEFAULT_STORE_VALUES[cfg.TAGS_AS])
        append_first_pubdate = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_FIRST_PUBDATE, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_FIRST_PUBDATE])
        append_first_pubdate_pl = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.APPEND_FIRST_PUBDATE_PL, cfg.DEFAULT_STORE_VALUES[cfg.APPEND_FIRST_PUBDATE_PL])
        try:
            lubimy_czytac_id = self.parse_lubimy_czytac_id(self.url)
        except:
            self.log.exception('Error parsing LubimyCzytac.pl id for url: %r'%self.url)
            lubimy_czytac_id = None

        try:
            title = self.parse_title(root)
        except:
            self.log.exception('Error parsing title for url: %r'%self.url)
            title = None

        try:
            authors = self.parse_authors(root)
        except:
            self.log.exception('Error parsing authors for url: %r'%self.url)
            authors = []

        # LC dokleja czasem autora do tytułu („Tytuł - Autor”) – usuwamy go
        if title and authors:
            title = title.strip()
            for author in authors:
                if title.endswith(" - " + author):
                    title = title[:-(len(author) + 3)].strip()
                    break

        try:
            translators = self.parse_translators(root)
        except:
            self.log.exception('Error parsing translators for url: %r'%self.url)
            translators = []

        if not title or not authors or not lubimy_czytac_id:
            if not title :
                self.log.error('LubimyCzytac.pl_id: %r Title: %r Authors: %r'%(lubimy_czytac_id, title, authors))
                self.log.error('Could not find LubimyCzytac.pl_id or title or authors for %r'%self.url)
            return

        mi = Metadata(title, authors)
        mi.set_identifier('lubimyczytac', lubimy_czytac_id)
        self.lubimy_czytac_id = lubimy_czytac_id

        # Wartości domyślne pól opcjonalnych – gdy parser rzuci wyjątek, zmienna
        # musi istnieć, inaczej składanie komentarza skończyłoby się UnboundLocalError
        serwyd = None
        rating_LC = None
        rating_LC_count = None
        pobrane_strony = None
        tytul_oryginalu = None
        inne_wydania = None
        inne_wydania_lista = None
        inne_wydania_short_lista = None
        tags = None
        tags_keywords = None

        try:
            serwyd = self.parse_serwyd(root)
        except:
            self.log.exception('Error parsing book series for url: %r'%self.url)
            serwyd = None


        try:
            (series, series_index) = self.parse_series(root)
        except:
            self.log.exception('Error parsing series (cykl) for url: %r'%self.url)
            series = series_index = None
        if series:
            mi.series = series
        if series and series_index:
            mi.series_index = series_index



        replaceISBN = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.REPLACE_ISBN, cfg.DEFAULT_STORE_VALUES[cfg.REPLACE_ISBN])
        self.log.info('BECKY INFO: Download ISBN number from LC: %s'%replaceISBN)
        if replaceISBN == 1:
            try:
                isbn = self.parse_isbn(root)
                if isbn:
                    self.isbn = mi.isbn = isbn
            except:
                self.log.exception('Error parsing ISBN for url: %r'%self.url)

        try:
            mi.rating = self.parse_rating(root)
        except:
            self.log.exception('Error parsing ratings (stars) for url: %r'%self.url)

        try:
            rating_LC = self.parse_rating_lc(root)
        except:
            self.log.exception('Error parsing ratings (number) for url: %r'%self.url)

        try:
            rating_LC_count = self.parse_rating_lc_count(root)
        except:
            self.log.exception('Error parsing ratings counts for url: %r'%self.url)
            rating_LC_count = None

        try:
            pobrane_strony = self.parse_pages(root)
        except:
            self.log.exception('Error parsing pages for url: %r'%self.url)
            pobrane_strony = None

        try:
            tytul_oryginalu = self.parse_tytul_oryginalu(root)
        except:
            self.log.exception('Error parsing original title for url: %r'%self.url)


        first_pubdate = None
        try:
            first_pubdate = self.parse_first_published_date(root)
        except:
            self.log.exception('Error parsing first publication date for url: %r'%self.url)

        first_pubdate_pl = None
        try:
            first_pubdate_pl = self.parse_first_published_date_pl(root)
        except:
            self.log.exception('Error parsing first publication date in Poland for url: %r'%self.url)

        try:
            inne_wydania = self.parse_inne_wydania(root)
        except:
            self.log.exception('Error parsing other editions for url: %r'%self.url)

        # Listy wydań wymagają pobrania osobnej strony, więc budujemy je tylko
        # wtedy, gdy któraś z opcji list jest włączona (do 2.4.1 – zawsze,
        # czyli jedno zbędne żądanie na każdego kandydata). Lista skrócona
        # korzysta z tytułów odczytanych przez listę pełną.
        if before_other_editions_all == 1 or before_other_editions_short == 1:
            try:
                inne_wydania_lista = self.parse_inne_wydania_all(root)
                if inne_wydania_lista:
                    self.log.info('BECKY INFO: Pelna lista innych wydan\n%s-----'%strip_accents(inne_wydania_lista))
            except:
                self.log.exception('Error parsing list of other editions for url: %r'%self.url)

        if before_other_editions_short == 1:
            try:
                inne_wydania_short_lista = self.parse_inne_wydania_short(root)
                if inne_wydania_short_lista:
                    self.log.info('BECKY INFO: Krotka lista innych wydan\n%s-----'%strip_accents(inne_wydania_short_lista).replace('•',  '*'))
            except:
                self.log.exception('Error parsing list of other editions for url: %r'%self.url)

        try:
            tags = self.parse_tags(root)
            tags_keywords = self.parse_tags_keywords(root)
            if asTags == 0:
                if tags:
                    # Kategorie jako etykiety. Calibre rozdziela etykiety
                    # przecinkami, więc przecinki wewnątrz kategorii zamieniamy na średniki
                    tags_ze_srednikami = [w.replace(',',  ';') for w in tags]
                    mi.tags = tags_ze_srednikami
                    self.log.info('BECKY INFO: Do pola Tags/Etykiety dopisano kategorie')
            else:
                if tags_keywords:
                    # Słowa kluczowe jako etykiety
                    mi.tags = tags_keywords
                    self.log.info('BECKY INFO: Do pola Tags/Etykiety dopisano slowa kluczowe')
            # Pierwsza litera każdej kategorii wielka; kategorie sklejamy w jeden
            # napis na potrzeby akapitu „Kategoria:” w komentarzu
            if tags is not None:
                tags = [re.sub('[a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]', lambda x: x.group().upper(), y, 1) for y in tags]
                tags = ''.join(tags)
            # Pierwsza litera każdego słowa kluczowego wielka
            if tags_keywords is not None:
                tags_keywords = [re.sub('[a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]', lambda x: x.group().upper(), y, 1) for y in tags_keywords]
        except:
            self.log.exception('Error parsing tags for url: %r'%self.url)

        try:
            try:
                mi.comments = self.parse_comments(root)
            except:
                self.log.exception('Error parsing comments for url: %r' % self.url)
                mi.comments = ''
            if (append_pages == 1) and (pobrane_strony is not None):
                if (append_pages_new == 0):
                    mi.comments = mi.comments + '<p id="strony">Książka ma ' + pobrane_strony + odmiana(pobrane_strony, frazastrona) + '.</p>'
                else:
                    # Uproszczona forma – łatwiejsza do parsowania przez inne narzędzia (METAmover)
                    mi.comments = mi.comments + '<p id="numberOfPages">Liczba stron w książce: ' + pobrane_strony + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono liczbe stron')

            if (append_original_title == 1) and (tytul_oryginalu is not None):
                mi.comments = mi.comments + '<p id="tytul_oryginalu">Tytuł oryginału: <em>' + tytul_oryginalu + '</em></p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono tytul oryginalu')

            if (append_translators == 1) and (translators is not None):
                mi.comments = mi.comments + '<p id="tlumaczenie">Tłumaczenie: ' + ', '.join(translators) + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono tlumaczy')

            if (append_serwyd == 1) and (serwyd is not None):
                mi.comments = mi.comments + '<p id="seria">Seria: ' + serwyd + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono nazwe serii wydawniczej')

            if (append_kategoria == 1) and (tags is not None):
                mi.comments = mi.comments + '<p id="kategoria">Kategoria: ' + tags + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono nazwe kategorii')

            if (append_keywords == 1) and (tags_keywords is not None):
                mi.comments = mi.comments + '<p id="slowa_kluczowe">Słowa kluczowe: ' + ', '.join(tags_keywords) + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono slowa kluczowe')

            if (append_rating == 1) and (lubimy_czytac_id is not None) and (rating_LC is not None):
                mi.comments = mi.comments + '<p id="ratingLC">Ocena w LC: ' + rating_LC + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono ocene z serwisu LubimyCzytac')

            if (append_rating_counts == 1) and (lubimy_czytac_id is not None) and (rating_LC_count is not None):
                mi.comments = mi.comments + '<p id="ratingLC_count">Liczba ocen w LC: ' + rating_LC_count + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono liczbe ocen z serwisu LubimyCzytac')

            if (append_first_pubdate == 1) and (first_pubdate is not None):
                mi.comments = mi.comments + '<p id="pierwsze_wydanie">Data pierwszego wydania: ' + first_pubdate.strftime("%d.%m.%Y") + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono date pierwszego wydania')

            if (append_first_pubdate_pl == 1) and (first_pubdate_pl is not None):
                mi.comments = mi.comments + '<p id="pierwsze_wydanie_pl">Data pierwszego wydania w Polsce: ' + first_pubdate_pl.strftime("%d.%m.%Y") + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono date pierwszego wydania w Polsce')

            if (append_id == 1) and (lubimy_czytac_id is not None):
                mi.comments = mi.comments + '<p id="lubimyczytac">ID: ' + lubimy_czytac_id + '</p>'
                self.log.info('BECKY INFO: Do komentarza dolaczono ID z serwisu LubimyCzytac')

            # Informacje o innych wydaniach trafiają PRZED opis – w odwrotnej
            # kolejności dopisywania, bo każda kolejna jest wstawiana na początek
            if (before_hr == 1) and (((before_other_editions_all == 1) and (inne_wydania_lista is not None)) or ((before_other_editions_short == 1) and (inne_wydania_short_lista is not None)) or ((before_other_editions_exist == 1) and (inne_wydania is not None))):
                mi.comments = '<hr id="przed-komentarzem">' + mi.comments

            if (before_other_editions_all == 1) and (inne_wydania_lista is not None):
                mi.comments = inne_wydania_lista + mi.comments

            if (before_other_editions_short == 1) and (inne_wydania_short_lista is not None):
                mi.comments = inne_wydania_short_lista + mi.comments

            if (before_other_editions_exist == 1) and (inne_wydania is not None):
                mi.comments = '<p>Inne wydania: <span style="color:red; font-weight: bold;">Istnieją inne wydania</span></p>' + mi.comments

        except:
            self.log.exception('Error parsing comments for url: %r'%self.url)

        try:
            mi.publisher = self.parse_publisher(root)
        except:
            self.log.exception('Error parsing publisher for url: %r'%self.url)

        try:
            mi.pubdate = self.parse_published_date(root)
        except:
            self.log.exception('Error parsing published date for url: %r'%self.url)

        try:
            languages = self.parse_languages(root)
            if languages:
                mi.languages = languages
        except:
            self.log.exception('Error parsing languages for url: %r'%self.url)

        try:
            self.cover_url = self.parse_cover(root)
        except:
            self.log.exception('Error parsing cover for url: %r'%self.url)
        mi.has_cover = bool(self.cover_url)

        # Pozycja kandydata na liście z identify() – ostatnie kryterium
        # sortowania wyników (patrz MetadataCompareKeyGen w __init__.py)
        mi.source_relevance = self.relevance

        # Pamięć podręczna wtyczki: ISBN -> ID LC oraz ID LC -> adres okładki
        # (wykorzystywana przez download_cover w __init__.py)
        if self.lubimy_czytac_id:
            if self.isbn:
                self.plugin.cache_isbn_to_identifier(self.isbn, self.lubimy_czytac_id)
            if self.cover_url:
                self.plugin.cache_identifier_to_cover_url(self.lubimy_czytac_id, self.cover_url)

        self.clean_downloaded_metadata(mi)
        self.log_parse_diagnostics()
        self.result_queue.put(mi)

    def parse_lubimy_czytac_id(self, url):
        """Wyciąga identyfikator LC z adresu strony książki lub audiobooka (``/ksiazka/<ID>/...``, ``/audiobook/<ID>/...``)."""
        return re.search('lubimyczytac.pl/(?:ksiazka|audiobook)/(\\d+)/.*', url).groups(1)[0]

    def parse_jsonld_node(self, json_node):
        """
        Parsuje treść jednego bloku ``<script type="application/ld+json">``.
        Zwraca ``None``, gdy JSON jest niepoprawny.

        LC czasem osadza w JSON-LD surowe znaki kontrolne (np. znaki nowej
        linii wewnątrz treści opinii użytkowników), co łamie specyfikację JSON.
        ``strict=False`` pozwala modułowi ``json`` zaakceptować takie dosłowne
        znaki kontrolne w napisach zamiast rzucać ``JSONDecodeError``.
        """
        try:
            return json.loads(json_node, strict=False)
        except (ValueError, TypeError):
            return None


    def get_jsonld_data(self, root, field=None):
        """
        Znajduje w JSON-LD obiekt typu ``Book`` lub ``Audiobook``.

        Bez parametru ``field`` zwraca cały obiekt (słownik). Z parametrem
        ``field`` zwraca **wartość** wskazanego pola – można podać ścieżkę
        z kropkami, np. ``'aggregateRating.ratingCount'``. Obsługuje listy
        obiektów oraz strukturę ``@graph``. Zwraca ``None``, gdy nic nie znaleziono.

        Uwaga: wywołując z ``field``, otrzymujemy od razu wartość pola –
        nie należy jej ponownie indeksować nazwą pola.
        """

        def iter_objects(data):
            """Rekurencyjnie wyszukuje obiekty Book/Audiobook (również w listach i ``@graph``)."""
            if isinstance(data, list):
                for item in data:
                    for obj in iter_objects(item):
                        yield obj

            elif isinstance(data, dict):
                graph = data.get('@graph')

                if isinstance(graph, list):
                    for item in graph:
                        for obj in iter_objects(item):
                            yield obj

                obj_type = data.get('@type')
                if not isinstance(obj_type, list):
                    obj_type = [obj_type]

                # Typ może być pełnym adresem schema.org – bierzemy ostatni człon
                normalized_types = [
                    str(item).rsplit('/', 1)[-1].rsplit('#', 1)[-1]
                    for item in obj_type
                    if item
                ]

                if 'Book' in normalized_types or 'Audiobook' in normalized_types:
                    yield data

        json_nodes = root.xpath(
            '//script[@type="application/ld+json"]/text()'
        )

        for json_node in json_nodes:
            data = self.parse_jsonld_node(json_node)

            if data is None:
                continue

            for book in iter_objects(data):
                if field is None:
                    return book

                value = book
                for key in field.split('.'):
                    if not isinstance(value, dict) or key not in value:
                        value = None
                        break
                    value = value[key]

                if value is not None:
                    return value

        return None


    def parse_title(self, root):
        """
        Tytuł książki. Źródła w kolejności: JSON-LD (``name``), atrybut
        ``data-title`` kontenera tytułu, ``og:title`` (po odcięciu części
        po „|” i doklejonego autora po „ - ”). Na końcu zamieniamy encje
        HTML; parę ``&quot;`` zastępujemy polskimi cudzysłowami „ ”.
        Zwraca ``None``, gdy tytułu nie udało się ustalić.
        """

        title_text = u''

        # 1. JSON-LD
        data = self.get_jsonld_data(root)

        if data:
            json_title = data.get('name')

            if json_title:
                title_text = json_title.strip()

                self.log.info(
                    'BECKY INFO: Found title (json): %s'
                    % strip_accents(unicode(str(title_text)))
                )

        # 2. data-title
        if not title_text:
            title_attr = root.xpath(
                '//div[contains(@class,"title-container")]/@data-title'
            )

            if title_attr:
                title_text = title_attr[0].strip()

                self.log.info(
                    'BECKY INFO: Found title (data-title): %s'
                    % strip_accents(unicode(str(title_text)))
                )

        # 3. og:title (ostatnia deska ratunku)
        if not title_text:
            try:
                title_text = root.xpath(
                    '//meta[@property="og:title"]/@content'
                )[0]

                title_text = title_text.split("|")[0]

                # LC czasem dodaje autorów po " - "
                if ' - ' in title_text:
                    title_text = title_text.split(' - ')[0]

                self.log.info(
                    'BECKY INFO: Found title (og:title): %s'
                    % strip_accents(unicode(str(title_text)))
                )

            except IndexError:
                self.log.error(
                    'BECKY ERROR: Problem z pobraniem tytulu.'
                )

        # 4. Encje HTML
        if title_text:
            title_text = (
                title_text
                .replace("&amp;", "&")
            )

            liczba_cudzyslowow = title_text.count("&quot;")

            if liczba_cudzyslowow == 2:
                # Dokładnie para cudzysłowów – zamieniamy na polskie „ ”
                title_text = title_text.replace(
                    "&quot;",
                    "„",
                    1
                )

                title_text = title_text.replace(
                    "&quot;",
                    "”",
                    1
                )

            else:
                title_text = title_text.replace(
                    "&quot;",
                    "\""
                )

            title_text = title_text.strip()

        if not title_text:
            return None

        return title_text


    def parse_authors(self, root):
        """
        Lista autorów (bez duplikatów). Źródła w kolejności: ``<meta
        books:author>`` (autorzy rozdzieleni przecinkami), atrybut
        ``data-ga-book-authors`` sekcji książki, JSON-LD (``author`` –
        obiekt lub lista obiektów ``Person``), wreszcie odsyłacze w HTML.
        Zwraca ``None``, gdy nie znaleziono żadnego autora.
        """

        authors = []

        # 1. <meta property="books:author">
        author_meta = root.xpath(
            '//meta[@property="books:author"]/@content'
        )

        if author_meta:
            authors_raw = author_meta[0]

            # Zamiana encji HTML
            authors_raw = authors_raw.replace('&nbsp;', ' ')

            for author in authors_raw.split(','):
                author = author.strip()

                if author and author not in authors:
                    self.log.info(
                        'BECKY INFO: Found author (meta): %s'
                        % strip_accents(unicode(str(author)))
                    )

                    authors.append(author)

        # 2. data-ga-book-authors
        if not authors:
            ga_authors = root.xpath(
                '//section[@id="container-book"]/@data-ga-book-authors'
            )

            if ga_authors:
                authors_raw = ga_authors[0]

                for author in authors_raw.split(','):
                    author = author.strip()

                    if author and author not in authors:
                        self.log.info(
                            'BECKY INFO: Found author (data-ga): %s'
                            % strip_accents(unicode(str(author)))
                        )

                        authors.append(author)

        # 3. JSON-LD
        if not authors:
            author_data = self.get_jsonld_data(root, 'author')

            if isinstance(author_data, dict):
                author_data = [author_data]

            if isinstance(author_data, list):
                for item in author_data:
                    if isinstance(item, dict):
                        author = item.get('name')

                        # unicode (six), nie str – w Pythonie 2 napisy z JSON są typu unicode
                        if isinstance(author, unicode):
                            author = author.strip()

                            if author and author not in authors:
                                self.log.info(
                                    'BECKY INFO: Found author (json): %s'
                                    % strip_accents(unicode(str(author)))
                                )
                                authors.append(author)

        # 4. Ostateczna deska ratunku – odsyłacze w HTML
        if not authors:
            author_nodes = root.xpath(
                '//span[contains(@class,"author")]//a'
            )

            for author_node in author_nodes:
                if author_node.text is not None:
                    author = author_node.text.strip()

                    if author and author not in authors:
                        self.log.info(
                            'BECKY INFO: Found author (html): %s'
                            % strip_accents(unicode(str(author)))
                        )

                        authors.append(author)

        if not authors:
            self.log.info(
                'Problem z pobraniem autora. Powiadom Becky o tym.'
            )
            return None

        return authors


    def parse_translators(self, root):
        """Lista tłumaczy (odsyłacze ``/tlumacz/`` przy etykiecie „Tłumacz:”) bez duplikatów; ``None``, gdy brak."""
        translator_nodes = root.xpath('//section[@class="container book"]//dt[contains(text(),"Tłumacz:")]/following-sibling::dd/a[contains(@href,"/tlumacz/")]')

        if translator_nodes:
            translators = []
            for translator_node in translator_nodes:
                if translator_node.text is not None and translator_node.text not in translators:
                    translator = translator_node.text.strip()
                    self.log.info('BECKY INFO: Found translator: %s'%strip_accents(unicode(str(translator))))
                    translators.append(translator)
            return unique(translators)

    def parse_serwyd(self, root):
        """
        Seria wydawnicza (etykieta „Seria:”, odsyłacz ``/seria/``) – w odróżnieniu
        od cyklu (``parse_series``) nie trafia do pola „Seria” w calibre, a jedynie
        opcjonalnie do komentarza. Zwraca nazwę serii albo ``None``.
        """
        try:
            serwyd_node = root.xpath('//section[@class="container book"]//dt[contains(text(),"Seria:")]/following-sibling::dd/a[contains(@href,"/seria/")]/text()')
            if serwyd_node:
                serwyd_lst = root.xpath('//section[@class="container book"]//a[contains(@href,"/seria/")]/text()')
                if serwyd_lst:
                    serwyd_txt = serwyd_lst[0]
                else:
                    serwyd_txt = None
            else:
                self.log.info('BECKY INFO: Not found book series (Nie znaleziono serii wydawniczej)')
                return None
            serwyd = serwyd_txt.strip()
            self.log.info('BECKY INFO: Found book series (Znaleziono serie wydawnicza): %s'%strip_accents(unicode(serwyd)))
            self.record_parse_attempt('publisher_series', 'HTML seria wydawnicza', serwyd)
            return serwyd
        except:
            return None

    def parse_series(self, root):
        """
        Cykl (odsyłacz ``/cykl/``) i numer tomu – trafiają do pól „Seria”
        i „Numer w serii” w calibre.

        LC zapisuje cykl jako „Nazwa cyklu (tom N)”. Numer tomu może być
        ułamkiem (np. 2.5) albo zakresem dla pakietów (np. „1-3” – bierzemy
        pierwszą liczbę). Gdy numeru nie da się odczytać, zwracamy 0.
        Zwraca krotkę ``(nazwa, numer)`` albo ``(None, None)``.
        """
        try:
            series_node = root.xpath('//section[@class="container book"]//span/a[contains(@href,"/cykl/")]')
            if series_node:
                series_lst = root.xpath('//section[@class="container book"]//span/a[contains(@href,"/cykl/")]/text()')
                if series_lst:
                    series_txt = series_lst
                else:
                    series_txt = None
            else:
                return (None, None)

            ser_info = None
            if series_txt:
                ser_string = [series_txt[0].replace('\n','').strip()]
                ser_nazwa = ser_string
                for ser in ser_string:
                    if 'tom ' in ser:
                        ser_info = ser.split(' (tom ', 1)
                        ser_nazwa = ser.split(' (tom ')[0]
                        break
            if ser_info:
                series_index_unicode = ser_info[1]
                series_index_string = str(series_index_unicode.replace(" ", "").replace(")", ""))
                # Pakiet/komplet tomów, np. „1-3” – bierzemy pierwszy numer
                if "-" in series_index_string:
                    series_index_string_temp = series_index_string.split('-', 1)
                    series_index_string = series_index_string_temp[0]
                if series_index_string.replace(".", "").isdigit() is True:
                    series_index = get_int_or_float(series_index_string)
                else:
                    series_index = 0
            else:
                series_index = 0
            series = ser_nazwa
            self.log.info('BECKY INFO: Found series (znaleziono cykl): (%s, %s)' % (strip_accents(unicode(series)), series_index))
            self.record_parse_attempt('series', 'HTML cykl', (series, series_index))
            return (series, series_index)
        except:
            return (None, None)

    def parse_rating(self, root):
        """
        Ocena w gwiazdkach calibre (0–5). LC ocenia w skali 1–10
        (``<meta books:rating:value>``), więc dzielimy przez 2 i zaokrąglamy.
        """
        rating_node = root.xpath('//meta[@property="books:rating:value"]/@content')
        if rating_node:
            self.log.info('BECKY INFO: Ocena w LC: %s'%rating_node[0])
            rating_value = round(float((rating_node[0]).replace(',','.'))/2)
            self.log.info('BECKY INFO: Found rating: %s'%rating_value)
            self.record_parse_attempt('rating_calibre', 'meta books:rating:value (przeliczenie /2)', rating_value)
            return rating_value
        return None

    def parse_rating_lc(self, root):
        """Ocena LC w postaci liczbowej (skala 1–10, kropka dziesiętna) – do komentarza. ``None``, gdy brak."""
        rating_node = root.xpath('//meta[@property="books:rating:value"]/@content')
        if rating_node:
            rating_LC = rating_node[0]
            rating_LC = rating_LC.replace(',','.')
            self.record_parse_attempt('rating_lc', 'meta books:rating:value', rating_LC)
            return rating_LC
        return None

    def parse_rating_lc_count(self,root):
        """Liczba ocen w LC (JSON-LD ``aggregateRating.ratingCount``) jako napis; ``None``, gdy brak."""
        # get_jsonld_data(root, pole) zwraca od razu wartość pola (tu: liczbę)
        rating_count_value = self.get_jsonld_data(root, 'aggregateRating.ratingCount')
        if not rating_count_value:
            return None
        rating_count = unicode(rating_count_value)
        self.log.info('BECKY INFO: Liczba ocen: %s'%rating_count)
        self.record_parse_attempt('rating_count', 'JSON-LD aggregateRating.ratingCount', rating_count)
        return rating_count

    def parse_isbn(self, root):
        """ISBN: najpierw ``<meta books:isbn>``, potem etykieta „ISBN:” w szczegółach książki. ``None``, gdy brak."""
        isbn_text = None
        try:
            isbn_node = root.xpath('//meta[@property="books:isbn"]/@content')[0]
        except IndexError:
            isbn_node = None

        if isbn_node:
            self.log.info('BECKY INFO: ISBN from meta: %s'%isbn_node)
            isbn_text = isbn_node
        else:
            self.log.info('BECKY INFO: Problem z numerem ISBN pobieranym z meta, ale probuje dalej...')

        if isbn_text is None:
            isbn_details = None
            data = self.parse_first(root,'//div[@id="book-details"]//dt[contains(text(),"ISBN:")]/following-sibling::dd[1]/text()','isbn')
            isbn_details = data.strip() if data else None

            if isbn_details is not None:
                self.log.info('BECKY INFO: ISBN from book-details: %s'%isbn_details)
                isbn_text = isbn_details
            else:
                self.log.info('BECKY INFO: Problem z numerem ISBN w book-details')
                isbn_text = None
        return isbn_text

    def parse_publisher(self, root):
        """Wydawnictwo (odsyłacz w ``span.book__txt`` zawierającym „Wydawnictwo:”). ``None``, gdy brak."""
        publisher = root.xpath('//span[contains(@class,"book__txt") and contains(normalize-space(.),"Wydawnictwo:")]//a/text()')
        if publisher:
            self.record_parse_attempt('publisher', 'HTML book__txt / Wydawnictwo', publisher[0])
            return publisher[0]
        else:
            self.record_parse_attempt('publisher', 'HTML book__txt / Wydawnictwo', None)
            return None

    def parse_published_date(self, root):
        """
        Data wydania tego konkretnego wydania: JSON-LD ``datePublished``
        (format ``RRRR-MM-DD``), awaryjnie etykieta „Data wydania:”
        w szczegółach książki. Zwraca ``datetime`` (patrz ``_convert_date_text``)
        albo ``None``.
        """
        # get_jsonld_data(root, pole) zwraca od razu wartość pola (napis z datą).
        # Niezrozumiała data z JSON-LD nie przerywa parsowania – przechodzimy
        # do ścieżki awaryjnej (HTML).
        pub_date = None
        pub_date_jsonld = self.get_jsonld_data(root, 'datePublished')
        if pub_date_jsonld:
            try:
                pub_date = self._convert_date_text(unicode(pub_date_jsonld).strip())
                self.record_parse_attempt('pubdate', 'JSON-LD datePublished', pub_date_jsonld)
            except ValueError:
                self.log.info('BECKY INFO: Niezrozumiala data wydania w JSON-LD: %s'%pub_date_jsonld)
                self.record_parse_attempt('pubdate', 'JSON-LD datePublished (niezrozumiala)', pub_date_jsonld)

        if pub_date is None:
            data = self.parse_first(root,'//div[@id="book-details"]//dt[contains(text(),"Data wydania:")]/following-sibling::dd[1]/text()','data_wydania')
            pub_date_details = data.strip() if data else None
            if pub_date_details is not None:
                pub_date = self._convert_date_text(pub_date_details)

        if pub_date is not None:
            self.log.info('BECKY INFO: Found publication date: %s'%pub_date)
        else:
            self.log.info('BECKY INFO: Not found publication date')
        return pub_date

    def parse_first_published_date(self, root):
        """Data pierwszego wydania oryginalnego (``dt`` z odpowiednim atrybutem ``title``). ``datetime`` albo ``None``."""
        first_pub_date_text = None
        data = self.parse_first(root,'//div[@id="book-details"]//dt[contains(@title,"Data pierwszego wydania oryginalnego")]/following-sibling::dd[1]/text()','data_first')
        first_pub_date_text = data

        if first_pub_date_text is not None:
            first_pub_date = self._convert_date_text_exact(first_pub_date_text.strip())
            self.log.info('BECKY INFO: Found first publication date: %s'%first_pub_date)
        else:
            self.log.info('BECKY INFO: Not found first publication date')
            first_pub_date = None
        return first_pub_date

    def parse_first_published_date_pl(self, root):
        """Data pierwszego wydania polskiego (``dt`` z odpowiednim atrybutem ``title``). ``datetime`` albo ``None``."""
        first_pub_date_pl_text = None
        data = self.parse_first(root,'//div[@id="book-details"]//dt[contains(@title,"Data pierwszego wydania polskiego")]/following-sibling::dd[1]/text()','data_first_pl')
        first_pub_date_pl_text = data

        if first_pub_date_pl_text is not None:
            first_pub_date_pl = self._convert_date_text_exact(first_pub_date_pl_text.strip())
            self.log.info('BECKY INFO: Found first publication date in Poland: %s'%first_pub_date_pl)
        else:
            self.log.info('BECKY INFO: Not found first publication date in Poland')
            first_pub_date_pl = None
        return first_pub_date_pl

    def _convert_date_text(self, date_text):
        """
        Zamienia napis ``RRRR-MM-DD`` na ``datetime`` dla pola „Data wydania”.

        Gdy data to 1 stycznia, zakładamy, że LC zna tylko rok, i przesuwamy
        ją na 1 lipca (środek roku) – data przybliżona nie leży wtedy na
        granicy lat. Godzina 14:00 to zabieg znany z innych wtyczek calibre:
        chroni przed przesunięciem daty o dzień przy przeliczaniu stref czasowych.
        Rzuca ``ValueError`` dla napisu w innym formacie.
        """
        year = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y'))
        month = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%m'))
        day = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%d'))
        if day == 1 and month == 1:
            month = 7
        return datetime.datetime(year, month, day, 14, 0, 0)

    def _convert_date_text_exact(self, date_text):
        """Jak ``_convert_date_text``, ale bez przesuwania 1 stycznia – dla dat pierwszych wydań w komentarzu."""
        year = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%Y'))
        month = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%m'))
        day = int(datetime.datetime.strptime(date_text, '%Y-%m-%d').strftime('%d'))
        return datetime.datetime(year, month, day, 14, 0, 0)

    def parse_pages(self, root):
        """
        Liczba stron jako napis z cyframi: JSON-LD ``numberOfPages``, awaryjnie
        etykieta „Liczba stron:” w szczegółach książki. ``None``, gdy brak
        (np. e-booki często nie mają liczby stron na LC) lub wartość nie jest liczbą.
        """
        # get_jsonld_data(root, pole) zwraca od razu wartość pola (napis „304”).
        # Sprawdzamy, czy to liczba, bo odmiana() wykonuje na niej int().
        pages = None
        pages_value = self.get_jsonld_data(root, 'numberOfPages')
        if pages_value:
            pages = unicode(pages_value).strip()
            if not pages.isdigit():
                self.log.info('BECKY INFO: Liczba stron w JSON-LD nie jest liczba: %s'%pages)
                pages = None
            else:
                self.record_parse_attempt('pages', 'JSON-LD numberOfPages', pages)
        if pages is None:
            data = self.parse_first(root,'//div[@id="book-details"]//dt[contains(text(),"Liczba stron:")]/following-sibling::dd[1]/text()','pages')
            if data:
                data = ''.join(ch for ch in unicode(data) if ch.isdigit())
                if data:
                    pages = data
        if pages is not None:
            self.log.info('BECKY INFO: Found number of pages: %s'%pages)
        else:
            self.log.info('BECKY INFO: Not found number of pages')
        return pages

    def parse_tytul_oryginalu(self, root):
        """Tytuł oryginału (etykieta „Tytuł oryginału” w szczegółach książki). ``None``, gdy brak."""
        tytul_oryginalu_node = self.parse_first(root,'//section[@class="container book"]//dt[contains(text(),"Tytuł oryginału")]/following-sibling::dd/text()','tytul_oryginalu')
        if tytul_oryginalu_node:
            tytul_oryginalu = tytul_oryginalu_node
        else:
            tytul_oryginalu = None
        return tytul_oryginalu

    def parse_inne_wydania(self, root):
        """
        Czy istnieją inne wydania książki – sprawdzamy obecność przycisku
        „Inne wydania”. Zwraca listę z tekstem przycisku (wartość prawdziwa)
        albo ``None``.
        """
        inne_wydania_istnieja = root.xpath('//button[@id="buttonShowOtherEditions"]/text()')
        if inne_wydania_istnieja:
            self.log.info('BECKY INFO: Istnieja inne wydania tej ksiazki')
        else:
            return None
        return inne_wydania_istnieja

    def parse_inne_wydania_all(self, root):
        """
        Pełna lista innych wydań jako akapit HTML z odsyłaczami
        (``<p id="lista-innych-wydan">``). ``None``, gdy brak innych wydań.

        Pełna lista znajduje się na osobnej stronie ``/ksiazka/wydania/<ID>/<slug>``,
        pobieranej przez ``fetch_editions_root`` (tylko gdy strona książki pokazuje
        inne wydania, najwyżej raz na Workera – tę samą stronę wykorzystuje skan
        ISBN). Jeśli jej pobranie się nie powiedzie, korzystamy ze skróconej listy
        osadzonej na stronie książki (``#other-editions``). Odczytane tytuły
        zapamiętujemy w ``self.inne_wydania_tytuly_short`` dla ``parse_inne_wydania_short``.
        """
        edition_links = self.edition_links(self.fetch_editions_root(root))

        # Ścieżka awaryjna na wypadek zmian po stronie serwisu lub problemów z połączeniem
        if not edition_links:
            links = root.xpath('//div[@id="other-editions"]/div/div//a')
            for node in links:
                href = node.get('href')
                img_alt = node.xpath('.//img/@alt')
                title = normalize_edition_title(img_alt[0] if img_alt else ''.join(node.itertext()))
                if href and title:
                    if href.startswith('/'):
                        href = 'https://lubimyczytac.pl' + href
                    if href not in [item[0] for item in edition_links]:
                        edition_links.append((href, title))

        if not edition_links:
            self.log.info('BECKY INFO: Brak linkow do innych wydan.')
            return None

        # Tytuły z pełnej listy wykorzystujemy również w liście skróconej.
        # Nie wyciągamy ich ze slugów URL, bo slug nie musi być tytułem.
        self.inne_wydania_tytuly_short = [title for href, title in edition_links]
        self.log.info('BECKY INFO: Znaleziono wydan: %d' % len(edition_links))
        self.log.info('BECKY INFO: Tytuly innych wydan (wszystkie):')
        self.log.info([strip_accents(unicode(title)) for href, title in edition_links])
        self.log.info('BECKY INFO: Linki do innych wydan:')
        inne_wydania_dane = '<br>'.join(
            '<a href="%s">%s</a>' % (href, html_escape(title))
            for href, title in edition_links
        )
        return '<p id="lista-innych-wydan">Lista innych wydań:<br>' + inne_wydania_dane + '</p>'

    def parse_inne_wydania_short(self, root):
        """
        Skrócona lista innych wydań – same tytuły, bez odsyłaczy i bez
        powtórzeń, jako akapit ``<p id="lista-innych-wydan-short">``.
        Powtórzenia wykrywamy po znormalizowanym kluczu (bez znaków
        diakrytycznych, małe litery, rozkodowane encje HTML, pojedyncze
        odstępy), ale wyświetlamy oryginalną pisownię. Treść akapitu zależy
        od tego, czy wszystkie wydania mają ten sam tytuł. ``None``, gdy brak wydań.

        Korzysta z tytułów odczytanych już przez ``parse_inne_wydania_all``;
        gdy ich nie ma, czyta ``#other-editions`` ze strony książki, a w ostateczności
        bierze końcówki (slugi) adresów.
        """
        inne_wydania_tytuly = self.inne_wydania_tytuly_short
        if not inne_wydania_tytuly:
            links = root.xpath('//div[@id="other-editions"]/div/div//a')
            inne_wydania_tytuly = []
            for node in links:
                img_alt = node.xpath('.//img/@alt')
                title = normalize_edition_title(img_alt[0] if img_alt else ''.join(node.itertext()))
                if title:
                    inne_wydania_tytuly.append(title)
            if not inne_wydania_tytuly:
                hrefs = root.xpath('//div[@id="other-editions"]/div/div//a/@href')
                inne_wydania_tytuly = [str(w.rpartition('/')[2]) for w in hrefs]
        inne_wydania_wszystkie_short = None
        lista_innych_wydan_short = None
        if inne_wydania_tytuly:
            # strip_accents służy wyłącznie do porównania – do komentarza trafia
            # oryginalna pisownia (z polskimi znakami)
            inne_wydania_tytuly = [normalize_edition_title(w) for w in inne_wydania_tytuly]
            # Usuwamy powtórzenia; z dwu wariantów pisowni zostaje ten „mniejszy”
            # leksykograficznie (czyli z wielkimi literami)
            inne_wydania_tytuly_bez_powtorzen = []
            klucze = []
            for chwiloword in inne_wydania_tytuly:
                klucz = strip_accents(chwiloword).lower()
                if klucz in klucze:
                    i = klucze.index(klucz)
                    inne_wydania_tytuly_bez_powtorzen[i] = min(chwiloword, inne_wydania_tytuly_bez_powtorzen[i])
                else:
                    klucze.append(klucz)
                    inne_wydania_tytuly_bez_powtorzen.append(chwiloword)
            inne_wydania_dane_short = ' • '.join(html_escape(t) for t in inne_wydania_tytuly_bez_powtorzen)
            if len(inne_wydania_tytuly_bez_powtorzen) == 1:

                if len(inne_wydania_tytuly) == 1:
                    inne_wydania_wszystkie_short = '<p id="lista-innych-wydan-short">Tytuł innego wydania: ' + inne_wydania_dane_short + '</p>'
                else:
                    inne_wydania_wszystkie_short = '<p id="lista-innych-wydan-short">Wszystkie inne wydania mają ten sam tytuł: ' + inne_wydania_dane_short + '</p>'
            else:
                inne_wydania_wszystkie_short = '<p id="lista-innych-wydan-short">Tytuły innych wydań: ' + inne_wydania_dane_short + '</p>'
        if inne_wydania_wszystkie_short:
            lista_innych_wydan_short = inne_wydania_wszystkie_short
        else:
            lista_innych_wydan_short = None
        return lista_innych_wydan_short

    def parse_comments(self, root):
        """
        Opis książki jako HTML oczyszczony funkcją calibre ``sanitize_comments_html``.
        Źródło: ``div#book-description`` (po usunięciu akapitów ``p.source``
        z informacją o pochodzeniu opisu), awaryjnie ``og:description``.
        Zwraca pusty napis, gdy opisu brak.
        """
        comments = ''

        description_node = root.xpath('//div[contains(@id,"book-description")]')

        if description_node:
            for zrodla in root.xpath('//p[@class="source"]'):
                zrodla.getparent().remove(zrodla)
            comments = tostring(description_node[0], method='html')
            comments = sanitize_comments_html(comments)

        else:
            description_node = root.xpath('//meta[@property="og:description"]/@content')
            if description_node:
                comments = description_node[0]
                comments = sanitize_comments_html(comments)
        return comments

    def parse_tags(self, root):
        """
        Kategoria książki (z nawigacji „breadcrumbs”, odsyłacze ``/ksiazki/k/``)
        jako lista napisów. Zapis „, itd.” zamieniamy na „ itd.”, żeby nie
        powstała osobna etykieta. ``None``, gdy brak.
        """
        tags = None
        try:
            tags_from_genre = root.xpath('//nav[@aria-label="breadcrumbs"]//a[contains(@href,"/ksiazki/k/")]/span[@itemprop="name"]/text()')
            if tags_from_genre:
                tags_from_genre_temp = strip_accents(unicode(''.join(tags_from_genre).strip()))
                self.log.info('BECKY INFO: Tags (genre): %s'%tags_from_genre_temp)
                tags = tags_from_genre
                tags = [w.replace(', itd.',  ' itd.') for w in tags]
                return tags
            else:
                self.log.info('BECKY INFO: No tags (genre)')
                return None
        except:
            return tags

    def parse_tags_keywords(self, root):
        """Słowa kluczowe (etykieta „Tagi:” w szczegółach książki) jako lista bez duplikatów. ``None``, gdy brak."""
        tags_keywords = list()
        try:
            tags_from_keywords = root.xpath('//section[@class="container book"]//dt[contains(text(),"Tagi:")]/following-sibling::dd/a/text()')
            if tags_from_keywords:
                for tag in tags_from_keywords:
                    if tag not in tags_keywords:
                        tags_keywords.append(tag.strip())
            if tags_keywords:
                self.log.info('BECKY INFO: Unikatowe tags (keywords): %s'%unique(tags_keywords))
                return unique(tags_keywords)
            else:
                self.log.info('BECKY INFO: No tags (keywords)')
                return None
        except:
            return list(tags_keywords)

    def parse_languages(self, root):
        """
        Języki książki jako lista kodów ISO 639-2 (``pol``, ``eng``) na
        podstawie etykiety „Język:”. Rozpoznajemy tylko polski i angielski;
        dla innych języków zwracamy pustą listę.
        """
        lang = self.parse_first(root,'//section[@class="container book"]//dt[contains(text(),"Język:")]/following-sibling::dd/text()','inLanguage')
        languages = list()
        if lang:
            self.record_parse_attempt('language', 'HTML etykieta Język', lang)
            if "polski" in lang:
                languages.append("pol")
            if "angielski" in lang:
                languages.append("eng")
        if not lang:
            self.record_parse_attempt('language', 'HTML etykieta Język', None)
        return languages


    def is_placeholder_cover(self, url):
        """
        ``True``, gdy adres wskazuje na obrazek zastępczy, a nie prawdziwą
        okładkę: logo LC, domyślną okładkę ``default-book-*`` lub plik SVG.
        Pusty adres również traktujemy jak brak okładki.
        """
        if not url:
            return True

        # Logo LC
        if 'lc-logo' in url:
            return True

        # Domyślna okładka zastępcza
        if 'default-book-' in url:
            return True

        # SVG placeholder
        if url.endswith('.svg'):
            return True

        return False


    def parse_cover(self, root):
        """
        Adres okładki. Źródła w kolejności: JSON-LD (``image``), ``<link
        rel="preload" as="image">``, ``<img>`` w ``div.book-cover``, ``og:image``
        – z pominięciem obrazków zastępczych (``is_placeholder_cover``).

        Na końcu sprawdzamy żądaniem HTTP, czy plik istnieje i nie jest
        podejrzanie mały (poniżej 1000 bajtów = uszkodzony obrazek).
        Zwraca adres albo ``None``.
        """
        img_url = None

        # 1. JSON-LD
        data = self.get_jsonld_data(root)

        if data:
            json_image = data.get('image')

            if json_image and not self.is_placeholder_cover(json_image):
                self.log.info(
                    'BECKY INFO: Found cover (json): %s'
                    % json_image
                )

                img_url = json_image

        # 2. <link rel="preload" as="image">
        if not img_url:
            preload_img = root.xpath(
                '//link[@rel="preload"][@as="image"]/@href'
            )

            if preload_img:
                if not self.is_placeholder_cover(preload_img[0]):
                    self.log.info(
                        'BECKY INFO: Found cover (preload): %s'
                        % preload_img[0]
                    )

                    img_url = preload_img[0]

        # 3. <img> w kontenerze okładki
        if not img_url:
            img_nodes = root.xpath(
                '//div[contains(@class,"book-cover")]//img/@src'
            )

            if img_nodes:
                if not self.is_placeholder_cover(img_nodes[0]):
                    self.log.info(
                        'BECKY INFO: Found cover (html): %s'
                        % img_nodes[0]
                    )

                    img_url = img_nodes[0]

        # 4. og:image (ostatnia deska ratunku)
        if not img_url:
            og_img = root.xpath(
                '//meta[@property="og:image"]/@content'
            )

            if og_img:
                if not self.is_placeholder_cover(og_img[0]):
                    self.log.info(
                        'BECKY INFO: Found cover (og:image): %s'
                        % og_img[0]
                    )

                    img_url = og_img[0]

        # 5. Walidacja adresu żądaniem HTTP
        if img_url:
            try:
                info = self.browser.open_novisit(
                    img_url,
                    timeout=self.timeout
                ).info()

            except:
                self.log.warning(
                    'BECKY HINT: Ten problem moze byc zwiazany z antywirusem lub firewallem'
                )

                info = None

            if info is not None:
                if info.get('Content-Length') is not None:
                    if int(info.get('Content-Length')) > 1000:
                        return img_url

                    else:
                        self.log.warning(
                            'Broken image for url: %s'
                            % img_url
                        )

                else:
                    return img_url

        return None

    def clean_downloaded_metadata(self, mi):
        """
        Końcowe porządki w metadanych – własna wersja metody z calibre
        (``Source.clean_downloaded_metadata``), celowo **bez** zmiany wielkości
        liter w tytule, którą calibre robi domyślnie.

        * ``fixauthors`` z calibre porządkuje zapis autorów;
        * przy opcji „Nazwisko Imię” przestawiamy człony nazw autorów;
        * każda etykieta zaczyna się wielką literą;
        * przy włączonym pobieraniu ISBN numer jest walidowany przez ``check_isbn``.
        """
        replaceISBN = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.REPLACE_ISBN, cfg.DEFAULT_STORE_VALUES[cfg.REPLACE_ISBN])
        swapnames = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.SWAP_NAMES, cfg.DEFAULT_STORE_VALUES[cfg.SWAP_NAMES])

        mi.authors = fixauthors(mi.authors)

        if swapnames:
            old_authors = mi.authors
            new_authors = [swap_names(a) for a in old_authors]
            mi.authors = new_authors
        # Pierwszą literę każdej etykiety dajemy od wielkiej litery
        mi.tags = [re.sub('[a-ząćęłńóśźżA-ZĄĆĘŁŃÓŚŹŻ]', lambda x: x.group().upper(), y, 1) for y in mi.tags]
        mi.tags = list(mi.tags)
        if replaceISBN == 1:
            mi.isbn = check_isbn(mi.isbn)

def get_int_or_float(v):
    """Zamienia napis na ``int``, gdy liczba jest całkowita (``'2.0'`` → 2), w przeciwnym razie na ``float`` (``'2.5'`` → 2.5)."""
    number_as_float = float(v)
    number_as_int = int(number_as_float)
    return number_as_int if number_as_float == number_as_int else number_as_float

def odmiana(x, y):
    """
    Dobiera polską formę rzeczownika do liczby ``x``.

    :param x: liczba (napis lub int)
    :param y: trzy formy: ``[mianownik l.poj., mianownik l.mn., dopełniacz l.mn.]``,
        np. ``["strona", "strony", "stron"]``
    :return: napis ze spacją na początku (np. ``" strony"``) albo ``" "`` dla zera

    Reguła: 1 → „strona”; liczby zakończone na 2–4 (ale nie na 12–14)
    → „strony”; pozostałe → „stron”.
    """
    x = int(x)
    if x == 0:
        return " "
    else:
        inumber = x % 10
        iinumber = x % 100
        if x == 1:
            y = y[0]
        elif iinumber > 4 and iinumber < 22:
            y = y[2]
        elif inumber>1 and inumber<=4:
            y = y[1]
        else:
            y = y[2]
        return " " + y

def strip_accents(s):
    """
    Zamienia polskie, węgierskie i niemieckie znaki diakrytyczne na ich
    odpowiedniki ASCII. Używana wyłącznie do komunikatów w logu – metadane
    zapisywane do calibre pozostają nietknięte. ``None`` przepuszcza bez zmian.
    """
    if s is None:
        return s
    else:
        symbols = ("öÖüÜóÓőŐúÚéÉáÁűŰíÍąĄćĆęĘłŁńŃóÓśŚźŹżŻ",
                   "oOuUoOoOuUeEaAuUiIaAcCeElLnNoOsSzZzZ")
        tr = dict([(ord(a), ord(b)) for (a, b) in zip(*symbols)])
        return s.translate(tr)

def normalize_edition_title(title):
    """
    Tytuł wydania do wyświetlenia i porównań: rozkodowane encje HTML
    (LC bywa podwójnie koduje znaki, np. „Arthur &amp; George”), pojedyncze
    odstępy, bez białych znaków na końcach. Pusty napis dla ``None``.
    """
    if not title:
        return ''
    title = html_unescape(unicode(title))
    return ' '.join(title.split())

def html_escape(text):
    """Minimalne kodowanie tekstu wstawianego do HTML komentarza (``&``, ``<``, ``>``)."""
    return unicode(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def unique(list1):
    """
    Zwraca listę bez duplikatów z zachowaniem kolejności pierwszych wystąpień.
    Używana także w ``LubimyCzytac.identify`` do odfiltrowania powtórzonych
    kandydatów bez psucia ich rankingu.
    """
    unique_list = []
    for x in list1:
        if x not in unique_list:
            unique_list.append(x)
    return unique_list


def swap_names(a):
    """
    Zamienia kolejność „Imię Nazwisko” <-> „Nazwisko Imię” dla opcji
    „W polu autorów stosuję zapis Nazwisko Imię”. Przy zapisie z przecinkiem
    („Nazwisko, Imię”) przenosi nazwisko na koniec; bez przecinka przenosi
    ostatni człon na początek. Nazwy jednoczłonowe zwraca bez zmian.

    Jedyna definicja tej funkcji – korzysta z niej zarówno ``clean_downloaded_metadata``
    (zapis metadanych), jak i ``LubimyCzytac.identify`` (ukryci autorzy w wyszukiwaniu).
    """
    if ',' in a:
        parts = a.split(',')
        if len(parts) <= 1:
            return a
        surname = parts[0]
        return '%s %s' % (' '.join(parts[1:]), surname)
    else:
        parts = a.split(None)
        if len(parts) <= 1:
            return a
        surname = parts[-1]
        return '%s %s' % (surname, ' '.join(parts[:-1]))
