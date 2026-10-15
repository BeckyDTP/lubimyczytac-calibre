# -*- coding: utf-8 -*-
"""
Limit czasu identify() (IDENTIFY_MAX_SECONDS): po jego przekroczeniu wtyczka
nie wysyła kolejnych zapytań do wyszukiwarki i przestaje czekać na Workery,
zwracając to, co zdążyły pobrać – zanim calibre zabije proces roboczy (300 s)
razem z dziennikiem.

    python3 test_deadline.py
"""
import os
import sys
import time
import unittest

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rare_cases
from rare_cases import FakeLog, Abort, set_config, make_plugin, lc_new, render_results
import lxml.html
from test_editions import FakeBrowser as EditionsBrowser


class SlowBrowser(EditionsBrowser):
    """Strona książki przychodzi z opóźnieniem – jak LC pod obciążeniem."""

    def __init__(self, delay, *a, **kw):
        EditionsBrowser.__init__(self, *a, **kw)
        self.delay = delay

    def open_novisit(self, url, timeout=None):
        if '/ksiazka/' in url and '/wydania/' not in url:
            time.sleep(self.delay)
        return EditionsBrowser.open_novisit(self, url, timeout)


def identify(plugin, title, authors):
    log = FakeLog()
    rq = Queue()
    plugin.identify(log, rq, Abort(), title=title, authors=authors)
    results = []
    while True:
        try:
            results.append(rq.get_nowait())
        except Empty:
            break
    return results, log


class DeadlineTests(unittest.TestCase):

    def setUp(self):
        set_config()
        self.saved = lc_new.IDENTIFY_MAX_SECONDS

    def tearDown(self):
        lc_new.IDENTIFY_MAX_SECONDS = self.saved

    def test_search_stops_issuing_queries_after_deadline(self):
        lc_new.IDENTIFY_MAX_SECONDS = -1          # limit miniety od razu
        plugin = make_plugin()
        calls = []
        def fetch(log, br, query, timeout):
            calls.append(query)
            return lxml.html.fromstring(render_results([]).encode('utf-8'))
        plugin._fetch_search_page = fetch
        results, log = identify(plugin, 'Historia jednej kropli', ['Aleksandra Jonasz-Zakrzewska'])
        self.assertEqual(calls, [], 'po limicie zadne zapytanie nie wychodzi')
        self.assertTrue(any('pomijam pozostale warianty zapytania (od 1/2)' in l for _, l in log.lines))
        self.assertEqual(results, [])

    def test_identify_returns_collected_results_when_worker_hangs(self):
        lc_new.IDENTIFY_MAX_SECONDS = 1
        books = {'100': ('Historia jednej kropli', '9788382907148', False),
                 '101': ('Historia jednej kropli', '9788300000101', False)}
        browser = SlowBrowser(3.0, books, [], '100')
        plugin = make_plugin()
        plugin.browser = browser
        page = render_results([['Historia jednej kropli', ['Aleksandra Jonasz-Zakrzewska'], '/ksiazka/100/x'],
                               ['Historia jednej kropli', ['Aleksandra Jonasz-Zakrzewska'], '/ksiazka/101/x']])
        plugin._fetch_search_page = lambda log, br, query, timeout: lxml.html.fromstring(page.encode('utf-8'))
        set_config(FAST_MATCH=False)
        started = time.time()
        results, log = identify(plugin, 'Historia jednej kropli', ['Aleksandra Jonasz-Zakrzewska'])
        elapsed = time.time() - started
        self.assertLess(elapsed, 2.5, 'identify nie czeka na wiszace Workery dluzej niz limit')
        self.assertTrue(any('limit czasu 1 s przekroczony' in l for _, l in log.lines))
        self.assertTrue(any(l.startswith('BECKY INFO: identify trwalo') for _, l in log.lines))
        self.assertEqual(results, [], 'Workery nie zdazyly niczego oddac')


if __name__ == '__main__':
    unittest.main(verbosity=2)
