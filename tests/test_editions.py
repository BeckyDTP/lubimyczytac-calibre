# -*- coding: utf-8 -*-
"""
Inne wydania bez zbędnych żądań: lista wydań pobierana tylko wtedy, gdy strona
książki pokazuje inne wydania i gdy któraś z opcji jej potrzebuje; skan ISBN
z limitem liczby stron i kolejnością „najpierw ten sam tytuł”. Atrapa LC
liczy żądania, więc każdy test mówi dokładnie, ile stron zostało pobranych.

    python3 test_editions.py
"""
import os
import sys
import unittest

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rare_cases                                   # ładuje pakiet wtyczki jako lc_new
from rare_cases import FakeLog, set_config, make_plugin, cfg
import importlib
worker = importlib.import_module('lc_new.worker')

BASE = 'https://lubimyczytac.pl'

BOOK_PAGE = u'''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta property="og:title" content="{title} - Autor Testowy | Książka w Lubimyczytac.pl">
<meta property="books:author" content="Autor Testowy">
<meta property="books:isbn" content="{isbn}">
<script type="application/ld+json">{{"@context":"http:\\/\\/schema.org","@type":"Book","name":"{title}","isbn":"{isbn}","datePublished":"2020-01-01","url":"https:\\/\\/lubimyczytac.pl\\/ksiazka\\/{id}\\/x","inLanguage":"polski","numberOfPages":"100","author":{{"@type":"Person","name":"Autor Testowy","url":"https:\\/\\/lubimyczytac.pl\\/autor\\/1\\/x"}}}}</script>
</head><body>
<section id="container-book" data-ga-book-authors="Autor Testowy">
<div class="title-container" data-title="{title}"><h1 class="book__title">{title}</h1></div>
<span class="author"><a href="/autor/1/x">Autor Testowy</a></span>
{editions_markup}
<div id="book-description"><p>Opis.</p></div>
<div id="book-details"><dl><dt>ISBN:</dt><dd>{isbn}</dd></dl></div>
</section></body></html>'''

EDITIONS_MARKUP = u'''<button id="buttonShowOtherEditions" type="button">Inne wydania</button>
<div class="collapse" id="other-editions"><a href="/ksiazka/wydania/{id}/{slug}"><span>więcej</span></a>
<div class="d-flex"><div><a href="/ksiazka/9001/x"><img alt="{title}"></a></div></div></div>'''

EDITIONS_PAGE_HEAD = u'<html><head><meta charset="utf-8"></head><body><div id="editionsList">'
EDITIONS_PAGE_TAIL = u'</div></body></html>'


def edition_card(book_id, title, kind='ksiazka'):
    return u'<div class="book-card"><a class="book-card__title" href="/%s/%s/x">%s</a></div>' % (kind, book_id, title)


class FakeResponse(object):
    def __init__(self, data):
        self._data = data
    def read(self):
        return self._data


class FakeBrowser(object):
    """Atrapa LC: strony książek z tabeli BOOKS, jedna lista wydań; liczy żądania."""

    def __init__(self, books, editions_cards, main_id):
        self.books = books              # id -> (title, isbn, has_editions)
        self.editions_cards = editions_cards
        self.main_id = main_id
        self.requests = []

    def clone_browser(self):
        return self

    def open_novisit(self, url, timeout=None):
        self.requests.append(url)
        if '/ksiazka/wydania/' in url:
            return FakeResponse((EDITIONS_PAGE_HEAD + u''.join(self.editions_cards) + EDITIONS_PAGE_TAIL).encode('utf-8'))
        for book_id, (title, isbn, has_editions) in self.books.items():
            if '/ksiazka/%s/' % book_id in url:
                markup = EDITIONS_MARKUP.format(id=self.main_id, slug='x', title=title) if has_editions else u''
                return FakeResponse(BOOK_PAGE.format(id=book_id, title=title, isbn=isbn, editions_markup=markup).encode('utf-8'))
        raise Exception('nieznany adres w atrapie: ' + url)


def run_worker(browser, book_id, target_isbn=None, **config):
    set_config(**config)
    plugin = make_plugin()
    log = FakeLog()
    rq = Queue()
    w = worker.Worker(BASE + '/ksiazka/%s/x' % book_id, rq, browser, log, 0, plugin, target_isbn=target_isbn)
    w.get_details()
    results = []
    while True:
        try:
            results.append(rq.get_nowait())
        except Empty:
            break
    return results, log, w


def requests_of(browser, fragment):
    return [u for u in browser.requests if fragment in u]


class NoEditionsTests(unittest.TestCase):
    """Książka bez innych wydań: nigdy nie pobieramy listy wydań."""

    def setUp(self):
        self.browser = FakeBrowser({'100': ('Samotna', '9788300000001', False)}, [], '100')

    def test_isbn_scan_skips_editions_list(self):
        results, log, w = run_worker(self.browser, '100', target_isbn='9788300000099', PREFER_ISBN_MATCH=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(requests_of(self.browser, '/wydania/'), [])
        self.assertTrue(any('pomijam pobieranie listy wydan' in l for _, l in log.lines))

    def test_lists_options_skip_editions_list(self):
        results, log, w = run_worker(self.browser, '100', BEFORE_OTHER_EDITIONS_ALL=True, BEFORE_OTHER_EDITIONS_SHORT=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(requests_of(self.browser, '/wydania/'), [])
        self.assertNotIn('Lista innych wyda', results[0].comments or '')


class WithEditionsTests(unittest.TestCase):
    """Książka z 30 wydaniami: jedno pobranie listy, skan ISBN z limitem i kolejnością."""

    def setUp(self):
        books = {'200': ('Pan Testeusz', '9788300000200', True)}
        cards = []
        # 29 innych wydan: tytul inny (edycja ilustrowana) na poczatku listy, potem ten sam tytul
        books['301'] = ('Pan Testeusz. Edycja ilustrowana', '9788300000301', True)
        cards.append(edition_card('301', 'Pan Testeusz. Edycja ilustrowana'))
        cards.append(edition_card('777', 'Pan Testeusz', kind='audiobook'))
        for i in range(2, 30):
            book_id = str(300 + i)
            books[book_id] = ('Pan Testeusz', '97883000%05d' % (300 + i), True)
            cards.append(edition_card(book_id, 'Pan Testeusz'))
        cards.append(edition_card('200', 'Pan Testeusz'))     # pierwotny kandydat na liscie
        self.books = books
        self.browser = FakeBrowser(books, cards, '200')

    def test_lists_fetched_once_and_only_when_option_on(self):
        results, log, w = run_worker(self.browser, '200')
        self.assertEqual(requests_of(self.browser, '/wydania/'), [], 'bez opcji list nie ma zadania o liste')
        self.browser.requests = []
        results, log, w = run_worker(self.browser, '200', BEFORE_OTHER_EDITIONS_ALL=True, BEFORE_OTHER_EDITIONS_SHORT=True)
        self.assertEqual(len(requests_of(self.browser, '/wydania/')), 1, 'lista pobrana dokladnie raz')
        self.assertIn('Lista innych wydań', results[0].comments)
        self.assertIn('lista-innych-wydan-short', results[0].comments)

    def test_isbn_scan_same_title_first_and_single_list_request(self):
        # szukane wydanie: 310 (ten sam tytul); edycja ilustrowana jest pierwsza na liscie, ale sprawdzana na koncu
        results, log, w = run_worker(self.browser, '200', target_isbn='9788300000310', PREFER_ISBN_MATCH=True,
                                     BEFORE_OTHER_EDITIONS_ALL=True)
        self.assertEqual(len(requests_of(self.browser, '/wydania/')), 1, 'lista pobrana raz dla skanu ISBN i listy w komentarzu')
        detail = [u for u in self.browser.requests if '/ksiazka/' in u and '/wydania/' not in u]
        self.assertEqual(detail[0], BASE + '/ksiazka/200/x')
        self.assertNotIn(BASE + '/ksiazka/301/x', detail, 'inny tytul sprawdzany dopiero po tych samych')
        self.assertNotIn(BASE + '/ksiazka/777/x', detail, 'audiobook pominiety')
        self.assertEqual(results[0].identifiers.get('lubimyczytac'), '310')
        self.assertTrue(any('DOKLADNA ZGODNOSC' in l for _, l in log.lines))

    def test_isbn_scan_respects_edition_limit(self):
        # ISBN, ktorego nie ma: skan konczy sie po ISBN_SCAN_MAX_EDITIONS stronach
        results, log, w = run_worker(self.browser, '200', target_isbn='9788399999999', PREFER_ISBN_MATCH=True)
        detail = [u for u in self.browser.requests if '/ksiazka/' in u and '/wydania/' not in u]
        self.assertEqual(len(detail), 1 + worker.ISBN_SCAN_MAX_EDITIONS)
        self.assertTrue(any('limit %d stron wydan osiagniety' % worker.ISBN_SCAN_MAX_EDITIONS in l for _, l in log.lines))
        self.assertEqual(results[0].identifiers.get('lubimyczytac'), '200', 'pozostaje pierwotne wydanie')

    def test_isbn_scan_time_budget(self):
        original = worker.ISBN_SCAN_MAX_SECONDS
        worker.ISBN_SCAN_MAX_SECONDS = -1          # kazda strona przekracza budzet
        try:
            results, log, w = run_worker(self.browser, '200', target_isbn='9788399999999', PREFER_ISBN_MATCH=True)
        finally:
            worker.ISBN_SCAN_MAX_SECONDS = original
        detail = [u for u in self.browser.requests if '/ksiazka/' in u and '/wydania/' not in u]
        self.assertEqual(len(detail), 1, 'po przekroczeniu budzetu czasu zadna strona wydania nie jest pobierana')
        self.assertTrue(any('limit czasu' in l for _, l in log.lines))

    def test_matching_isbn_on_main_edition_needs_no_requests(self):
        results, log, w = run_worker(self.browser, '200', target_isbn='9788300000200', PREFER_ISBN_MATCH=True)
        self.assertEqual(len(self.browser.requests), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
