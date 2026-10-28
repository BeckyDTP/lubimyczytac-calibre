# -*- coding: utf-8 -*-
"""
Cykl (pole „Seria” w calibre): nazwa zawsze napisem, numer tomu liczbą albo
``None``. Regresja zgłoszenia z 2026-10-27 – „Grim i Oro. Starcie dwóch koron”
(LC 5220403) należy do cyklu „Lightlark” bez numeru tomu; do 2.4.3 nazwa
trafiała do ``mi.series`` jako lista jednoelementowa i calibre przerywało
pobieranie przy zapisie wyniku do OPF (``TypeError: Argument must be bytes or
unicode, got 'list'``). Do tego strażnik typów ``ensure_metadata_types``.

    python3 test_series.py
"""
import os
import sys
import unittest

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rare_cases                                   # ładuje pakiet wtyczki jako lc_new
from rare_cases import FakeLog, set_config, make_plugin
from test_editions import BOOK_PAGE, FakeResponse, run_worker, BASE
import importlib
worker = importlib.import_module('lc_new.worker')
from queue import Queue

# Tak LC zapisuje cykl na stronie książki: w sekcji „container book”,
# w span-ie z odsyłaczem /cykl/; numer tomu – jeśli jest – w tym samym tekście
CYCLE_MARKUP = (u'<section class="container book"><span class="d-sm-block book__txt">Cykl: '
                u'%s</span></section>')
CYCLE_LINK = u'<a href="https://lubimyczytac.pl/cykl/118500/lightlark">%s</a>'


class PageBrowser(object):
    """Atrapa LC oddająca jedną, z góry zadaną stronę książki."""

    def __init__(self, html):
        self.html = html
        self.requests = []

    def clone_browser(self):
        return self

    def open_novisit(self, url, timeout=None):
        self.requests.append(url)
        return FakeResponse(self.html.encode('utf-8'))


def book_page(cycle_text, book_id='5220403', title=u'Grim i Oro. Starcie dwóch koron'):
    links = u''.join(CYCLE_LINK % txt for txt in cycle_text) if isinstance(cycle_text, (list, tuple)) \
        else CYCLE_LINK % cycle_text
    return BOOK_PAGE.format(id=book_id, title=title, isbn='9788383612201', editions_markup=CYCLE_MARKUP % links)


def identify_book(cycle_text):
    results, log, w = run_worker(PageBrowser(book_page(cycle_text)), '5220403')
    return results[0], log


class SplitSeriesVolumeTests(unittest.TestCase):
    """Czysty rozbiór tekstu „Nazwa (tom N)”."""

    def test_table(self):
        cases = [
            (u'Lightlark (tom 3)', (u'Lightlark', 3)),
            (u'Lightlark', (u'Lightlark', None)),              # cykl bez numeru – przypadek ze zgłoszenia
            (u'Cykl (tom 2.5)', (u'Cykl', 2.5)),
            (u'Cykl (tom 2,5)', (u'Cykl', 2.5)),
            (u'Cykl (tom 1-3)', (u'Cykl', 1)),                 # pakiet tomów – pierwszy numer
            (u'Cykl (tom 0)', (u'Cykl', 0)),                   # prequel
            (u'Cykl (tom I)', (u'Cykl', None)),                # numer nieczytelny
            (u'Cykl (TOM 4)', (u'Cykl', 4)),
            (u'\n  Świat Dysku\xa0(tom 12)\n', (u'Świat Dysku', 12)),
            (u'Cykl (nowy) (tom 2)', (u'Cykl (nowy)', 2)),
        ]
        for text, expected in cases:
            self.assertEqual(worker.split_series_volume(text), expected, text)
            self.assertIsInstance(worker.split_series_volume(text)[0], str)


class ParseSeriesTests(unittest.TestCase):
    """Worker na atrapie LC: co trafia do mi.series i mi.series_index."""

    def test_cycle_without_volume_is_a_string(self):
        mi, log = identify_book(u'Lightlark')
        self.assertIsInstance(mi.series, str)
        self.assertEqual(mi.series, u'Lightlark')
        self.assertIsNone(mi.series_index, 'LC nie podaje numeru - calibre zostawia swoj')
        self.assertTrue(any('cykl bez numeru tomu' in l for _, l in log.lines))
        # dokladnie ta operacja wywalala calibre (metadata_to_opf -> atrybut XML)
        etree.Element('meta', name='calibre:series', content=mi.series)
        with self.assertRaises(TypeError):
            etree.Element('meta', name='calibre:series', content=[u'Lightlark'])

    def test_cycle_with_volume(self):
        mi, log = identify_book(u'Lightlark (tom 3)')
        self.assertEqual((mi.series, mi.series_index), (u'Lightlark', 3))

    def test_volume_zero_is_kept(self):
        mi, log = identify_book(u'Lightlark (tom 0)')
        self.assertEqual(mi.series_index, 0, 'do 2.4.3 tom 0 przepadal jako wartosc falszywa')

    def test_whitespace_from_html(self):
        mi, log = identify_book(u'\n   Lightlark\xa0(tom 2)   \n')
        self.assertEqual((mi.series, mi.series_index), (u'Lightlark', 2))

    def test_two_cycles_first_wins(self):
        mi, log = identify_book([u'Lightlark (tom 3)', u'Grim i Oro (tom 1)'])
        self.assertEqual((mi.series, mi.series_index), (u'Lightlark', 3))
        self.assertTrue(any('nalezy do 2 cykli' in l for _, l in log.lines))

    def test_no_cycle(self):
        html = BOOK_PAGE.format(id='100', title=u'Samotna', isbn='9788300000001', editions_markup=u'')
        results, log, w = run_worker(PageBrowser(html), '100')
        self.assertIsNone(results[0].series)
        self.assertIsNone(results[0].series_index)


class EnsureMetadataTypesTests(unittest.TestCase):
    """Strażnik typów: naprawia i ostrzega; na poprawnych danych milczy."""

    def setUp(self):
        set_config()
        self.log = FakeLog()
        self.w = worker.Worker(BASE + '/ksiazka/1/x', Queue(), PageBrowser(u''), self.log, 0, make_plugin())
        self.Metadata = worker.Metadata

    def warnings(self):
        return [l for lvl, l in self.log.lines if lvl == 'WARN']

    def test_fixes_wrong_types(self):
        mi = self.Metadata([u'Tytuł', u'drugi'], [u'Autor Testowy'])
        mi.authors = u'Autor Testowy'
        mi.series = [u'Lightlark']
        mi.publisher = (u'Wydawca',)
        mi.comments = [u'<p>a</p>', u'<p>b</p>']
        mi.tags = u'fantasy'
        mi.languages = ('pol',)
        mi.series_index = u'2,5'
        mi.rating = u'abc'
        mi.identifiers = {'lubimyczytac': 5220403}
        self.w.ensure_metadata_types(mi)
        self.assertEqual(mi.title, u'Tytuł, drugi')
        self.assertEqual(mi.series, u'Lightlark')
        self.assertEqual(mi.publisher, u'Wydawca')
        self.assertEqual(mi.comments, u'<p>a</p><p>b</p>')
        self.assertEqual(mi.authors, [u'Autor Testowy'])
        self.assertEqual(mi.tags, [u'fantasy'])
        self.assertEqual(mi.languages, ['pol'])
        self.assertEqual(mi.series_index, 2.5)
        self.assertIsNone(mi.rating)
        self.assertEqual(mi.identifiers['lubimyczytac'], u'5220403')
        self.assertTrue(all(l.startswith('BECKY WARN:') for l in self.warnings()))
        self.assertEqual(len(self.warnings()), 9)

    def test_silent_on_correct_types(self):
        mi = self.Metadata(u'Tytuł', [u'Autor Testowy'])
        mi.series, mi.series_index, mi.rating, mi.tags = u'Lightlark', 0, 4, [u'fantasy']
        mi.identifiers = {'lubimyczytac': u'5220403', 'isbn': None}
        self.w.ensure_metadata_types(mi)
        self.assertEqual(self.warnings(), [])
        self.assertEqual((mi.series, mi.series_index, mi.rating), (u'Lightlark', 0, 4))


if __name__ == '__main__':
    unittest.main(verbosity=2)
