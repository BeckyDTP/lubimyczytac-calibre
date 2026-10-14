# -*- coding: utf-8 -*-
"""
Podpowiedź ręcznego wyszukania (opcja „Suggest a manual search when nothing
is found”): wirtualny wynik z linkami ma trafić do calibre tylko wtedy, gdy
LC nic nie znalazło, opcja jest włączona i wtyczka działa w oknie
pojedynczego pobierania. Bez calibre i bez sieci – atrapy z harness/stubs.

    python3 test_hint.py
"""
import io
import os
import re
import sys
import unittest

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rare_cases                                   # ładuje pakiet wtyczki jako lc_new
from rare_cases import FakeLog, Abort, set_config, make_plugin, lc_new, cfg
import lxml.html

EMPTY_PAGE = lxml.html.fromstring('<html><body><div id="ksiazki"></div></body></html>')


def run_identify(mode, suggest, title='Twarzyczka', authors=('Sophie Hannah',)):
    """Przebieg identify() z pustą stroną wyników LC i wymuszonym trybem pobierania."""
    set_config(SUGGEST_MANUAL_SEARCH=suggest)
    plugin = make_plugin()
    plugin._fetch_search_page = lambda log, br, query, timeout: EMPTY_PAGE
    original = lc_new.detect_download_mode
    lc_new.detect_download_mode = lambda: mode
    try:
        log = FakeLog()
        rq = Queue()
        plugin.identify(log, rq, Abort(), title=title, authors=list(authors) if authors else None)
    finally:
        lc_new.detect_download_mode = original
    results = []
    while True:
        try:
            results.append(rq.get_nowait())
        except Empty:
            break
    return results, log


class ManualSearchHintTests(unittest.TestCase):

    def test_hint_only_in_single_window(self):
        results, log = run_identify('single', True)
        self.assertEqual(len(results), 1)
        mi = results[0]
        self.assertEqual(mi.title, 'Twarzyczka')
        self.assertEqual(mi.authors, ['Sophie Hannah'])
        self.assertEqual(mi.identifiers, {})
        self.assertIn('site%3Alubimyczytac.pl%20%22Twarzyczka%22%20Sophie%20Hannah', mi.comments)
        self.assertIn('lubimyczytac:74063', mi.comments)
        self.assertTrue(any('BECKY HINT: dodaje wirtualny wynik' in l for _, l in log.lines))

    def test_no_hint_in_bulk_or_unknown_mode(self):
        for mode in ('bulk', 'unknown'):
            results, log = run_identify(mode, True)
            self.assertEqual(results, [], mode)
            self.assertTrue(any('podpowiedz recznego wyszukania pominieta (tryb: %s)' % mode in l for _, l in log.lines), mode)

    def test_no_hint_when_option_disabled(self):
        results, log = run_identify('single', False)
        self.assertEqual(results, [])
        self.assertFalse(any('BECKY HINT' in l for _, l in log.lines))

    def test_no_hint_without_title(self):
        results, log = run_identify('single', True, title='', authors=('Sophie Hannah',))
        self.assertEqual(results, [])

    def test_mode_is_logged(self):
        results, log = run_identify('single', False)
        self.assertTrue(any(re.match(r'BECKY INFO: tryb pobierania: single$', l) for _, l in log.lines))


if __name__ == '__main__':
    unittest.main(verbosity=2)
