# -*- coding: utf-8 -*-
"""
Rzadkie przypadki (inne wydania / zmiana tytułu / brak autora) – przebieg
`_search` wtyczki 2.4.0 na NAGRANYCH wynikach żywej wyszukiwarki LC.

  python3 rare_cases.py queries  > queries.json     # jakie adresy zapyta wtyczka
  (adresy pobiera przeglądarka -> recorded.json: {url: [[tytul, [autorzy], href], ...]})
  python3 rare_cases.py run recorded.json           # przebieg _search na nagraniach
"""
import sys, os, json, builtins, re, io
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
H = os.path.join(HERE, 'harness')
sys.path.insert(0, os.path.join(H, 'stubs'))
builtins._ = lambda s: s
import lxml.html


def load_plugin_package(root=None):
    """
    Ładuje kod wtyczki jako pakiet ``lc_new`` wprost z katalogu repozytorium
    (domyślnie: katalog nadrzędny ``tests/``), bez dowiązań symbolicznych.
    Ścieżkę można nadpisać zmienną środowiskową ``LC_PLUGIN_DIR``.
    """
    root = root or os.environ.get('LC_PLUGIN_DIR') or os.path.dirname(HERE)
    init = os.path.join(root, '__init__.py')
    if not os.path.isfile(init):
        raise SystemExit('Nie znaleziono %s – ustaw LC_PLUGIN_DIR na katalog z kodem wtyczki.' % init)
    spec = importlib.util.spec_from_file_location('lc_new', init, submodule_search_locations=[root])
    module = importlib.util.module_from_spec(spec)
    sys.modules['lc_new'] = module
    spec.loader.exec_module(module)
    return module


lc_new = load_plugin_package()
cfg = importlib.import_module('lc_new.config')
from calibre.utils.localization import get_udc

# (nazwa, tytuł w calibre, autorzy w calibre, {id: ocena}, oczekiwanie)
# ocena: OK = właściwe wydanie, ok = właściwa książka (inne wydanie), ZLE = inna książka
# oczekiwanie = (rodzaj wyniku, ID pierwszego kandydata albo None) dla bieżącej wersji;
# rodzaj: MOCNY (tytuł i autor), slaby (tylko tytuł albo tylko autor), brak.
# Wiersze oznaczone „znane ograniczenie” opisują zachowanie przyjęte świadomie –
# zmiana wyniku w tych wierszach to sygnał do ponownej analizy, nie błąd testu.
CASES = [
    # --- zmiana tytułu między wydaniami (Grisham: 16 wydań, 3 polskie tytuły) ---
    ('Grisham: Król odszkodowań (tytuł główny LC)', 'Król odszkodowań', ['John Grisham'],
     {'5001504': 'OK'}, ('MOCNY', '5001504')),
    # znane ograniczenie: LC nie ma „Król afer” jako tytułu głównego; wydanie zbiorcze zostaje słabą rezerwą
    ('Grisham: Król afer (Amber 2003; w LC tylko jako inne wydanie)', 'Król afer', ['John Grisham'],
     {'126907': 'OK', '199849': 'OK', '52298': 'OK', '303263': 'OK', '198068': 'OK', '268736': 'OK', '4996323': 'OK',
      '5001504': 'ok', '77020': 'ZLE (zbiorcze: Król afer; Ostatni sędzia; Wielki gracz)'}, ('slaby', '77020')),
    ('Grisham: Król pozwów (Albatros; w LC tylko jako inne wydanie)', 'Król pozwów', ['John Grisham'],
     {'74063': 'OK', '5001504': 'ok'}, ('brak', None)),
    # znane ograniczenie: zbiorcze + trzy książki „Adwokat” innych autorów jako słabe dopasowania tytułu
    ('Grisham: Uliczny adwokat (brak takiego wydania w LC)', 'Uliczny adwokat', ['John Grisham'],
     {'5104358': 'ok (Obrońca ulicy)', '66185': 'ZLE (zbiorcze KSIĄŻKI WYBRANE)', '69067': 'ZLE (Adwokat, Harr)',
      '60229': 'ZLE (Adwokat, Margolin)', '306647': 'ZLE (Adwokat, Singer)'}, ('slaby', '66185')),
    ('Grisham: Wielki gracz', 'Wielki gracz', ['John Grisham'], {'5181092': 'OK'}, ('MOCNY', '5181092')),
    ('Grisham: Ułaskawienie', 'Ułaskawienie', ['John Grisham'], {'4936252': 'OK'}, ('MOCNY', '4936252')),
    # --- King ---
    ('King: Miasteczko Salem', 'Miasteczko Salem', ['Stephen King'], {'5176146': 'OK'}, ('MOCNY', '5176146')),
    # „Salem” innych autorów pasuje częściowo do tytułu, „Miasteczko Salem” do autora; odsiew po pobraniu stron zostawia Kinga
    ('King: Dola Salem (brak w LC)', 'Dola Salem', ['Stephen King'],
     {'5176146': 'ok (Miasteczko Salem)', '5217109': 'ZLE (Salem, Alvares/Daniels)'}, ('slaby', '5217109')),
    ('King: Carrie', 'Carrie', ['Stephen King'], {'5264193': 'OK'}, ('MOCNY', '5264193')),
    # --- Orwell ---
    ('Orwell: Folwark zwierzęcy', 'Folwark zwierzęcy', ['George Orwell'], {'5242115': 'OK'}, ('MOCNY', '5242115')),
    # tytułu nie ma w LC: zostają książki „Zwierzyniec” innych autorów (słabe dopasowanie tytułu)
    ('Orwell: Zwierzyniec (brak w LC)', 'Zwierzyniec', ['George Orwell'],
     {'5242115': 'ok', '4900230': 'ZLE (Zwierzyniec, Bralczyk)', '105033': 'ZLE (Zwierzyniec, Brzechwa)',
      '4952417': 'ZLE (Zwierzyniec, da Vinci)', '210906': 'ZLE (Zwierzyniec, Matławska)'}, ('slaby', '4900230')),
    ('Orwell: Bunt zwierząt (brak w LC)', 'Bunt zwierząt', ['George Orwell'], {'5242115': 'ok'}, ('brak', None)),
    # --- Dick ---
    ('Dick: Czy androidy śnią… (LC: „Blade Runner. Czy androidy marzą…”)', 'Czy androidy śnią o elektrycznych owcach?',
     ['Philip K. Dick'], {'5241617': 'OK'}, ('slaby', '5241617')),
    # znane ograniczenie: LC nie ma wydania „Łowca androidów”; zostaje opracowanie o filmie
    ('Dick: Łowca androidów', 'Łowca androidów', ['Philip K. Dick'],
     {'5241617': 'ok', '4799056': 'ZLE (Tuziak: Łowca androidów. Słowa i obrazy)'}, ('slaby', '4799056')),
    # --- Christie ---
    ('Christie: Dziesięciu Murzynków', 'Dziesięciu Murzynków', ['Agatha Christie'],
     {'5251885': 'OK', '4971805': 'ok'}, ('MOCNY', '5251885')),
    ('Christie: I nie było już nikogo', 'I nie było już nikogo', ['Agatha Christie'], {'4971805': 'OK'}, ('MOCNY', '4971805')),
    # --- Hannah (Buźka / Twarzyczka – przypadek z forum eksiazki 2017) ---
    ('Hannah: Buźka', 'Buźka', ['Sophie Hannah'], {'257761': 'OK', '5063812': 'OK'}, ('MOCNY', '257761')),
    ('Hannah: Twarzyczka (Marginesy; w LC tylko jako inne wydanie)', 'Twarzyczka', ['Sophie Hannah'],
     {'20677': 'OK', '257761': 'ok', '5063812': 'ok'}, ('brak', None)),
    ('Hannah: Twarzyczka bez autora', 'Twarzyczka', None, {'20677': 'OK', '257761': 'ok'}, ('brak', None)),
    # --- Hobb: MAG 2 tomy vs Vesper 1 tom ---
    ('Hobb: Czarodziejski statek (Vesper, 1 tom)', 'Czarodziejski statek', ['Robin Hobb'],
     {'5260806': 'OK', '4805': 'ok (cz.1 MAG)', '4437': 'ok (cz.2 MAG)'}, ('MOCNY', '5260806')),
    ('Hobb: Czarodziejski statek cz.1 (MAG)', 'Czarodziejski statek cz.1', ['Robin Hobb'],
     {'4805': 'OK', '5260806': 'ZLE (wydanie jednotomowe Vesper)', '4437': 'ZLE (cz.2)'}, ('MOCNY', '4805')),
    # --- ten sam tytuł, różni wydawcy (kontrola) ---
    ('Tolkien: Hobbit, czyli tam i z powrotem', 'Hobbit, czyli tam i z powrotem', ['J.R.R. Tolkien'],
     {'5121473': 'OK'}, ('MOCNY', '5121473')),
    ('Herbert: Diuna', 'Diuna', ['Frank Herbert'], {'4942534': 'OK'}, ('MOCNY', '4942534')),
    ('Follett: Filary Ziemi', 'Filary Ziemi', ['Ken Follett'], {'5082323': 'OK'}, ('MOCNY', '5082323')),
    ('Adams: Autostopem przez Galaktykę', 'Autostopem przez Galaktykę', ['Douglas Adams'],
     {'4964197': 'OK', '5156405': 'ok (edycja ilustrowana)'}, ('MOCNY', '4964197')),
    ('Wharton: Ptasiek', 'Ptasiek', ['William Wharton'], {'5211207': 'OK'}, ('MOCNY', '5211207')),
    ('Collins: Igrzyska śmierci', 'Igrzyska śmierci', ['Suzanne Collins'],
     {'8546': 'OK', '238924': 'ZLE (Trylogia)'}, ('MOCNY', '8546')),
    # --- przypadki z forów ---
    ('Forum: Pomnik Cesarzowej Achai - Tom I (M[259])', 'Pomnik Cesarzowej Achai - Tom I', ['Andrzej Ziemiański'],
     {'128272': 'OK', '214735': 'ZLE (Tom IV)', '159773': 'ZLE (Tom II)'}, ('MOCNY', '128272')),
    ('Forum: Cała prawda o planecie Ksi (M[260])', 'Cała prawda o planecie Ksi', ['Janusz A. Zajdel'],
     {'111247': 'OK', '4143': 'ZLE (zbiór z „Drugim spojrzeniem”)'}, ('MOCNY', '111247')),
    ('Forum: Moje szczęśliwe małżeństwo #04 (M[211])', 'Moje szczęśliwe małżeństwo #04', ['Akumi Agitogi'],
     {'5180397': 'OK', '5131214': 'ZLE (#2)', '5113896': 'ZLE (#1)', '5168220': 'ZLE (#3)'}, ('MOCNY', '5180397')),
    ('Forum: Z Powstania Warszawskiego do Auschwitz (M[187], LC bez „Warszawskiego”)',
     'Z Powstania Warszawskiego do Auschwitz', ['Nina Majewska-Brown'], {'5069975': 'OK'}, ('slaby', '5069975')),
    ('Forum: Ucieczka (Muchamore, E[11])', 'Ucieczka', ['Robert Muchamore'], {'55416': 'OK'}, ('MOCNY', '55416')),
    ('Forum: Władca Barcelony (M[220])', 'Władca Barcelony', ['Chufo Lloréns'],
     {'23171': 'ok (starsze)', '310529': 'ok (nowsze)'}, ('MOCNY', '23171')),
    ('Forum: Medicus (M[81])', 'Medicus', ['Noah Gordon'], {'5026112': 'OK', '115399': 'ZLE (Spadkobierczyni Medicusa)'},
     ('MOCNY', '5026112')),
    ('Forum: Nowe życie (Kościelniak, M[195])', 'Nowe życie', ['Ewelina Kościelniak'],
     {'4808354': 'OK', '5062171': 'ZLE (Jax)'}, ('MOCNY', '4808354')),
    ('Forum: Wojna (Ostrowski, E[219])', 'Wojna', ['Jacek Ostrowski'],
     {'4963378': 'OK', '4185215': 'ZLE (Lewicki)'}, ('MOCNY', '4963378')),
    ('Forum: Rozgrywka (Reynolds, E[221])', 'Rozgrywka', ['Allie Reynolds'],
     {'4950038': 'OK', '4955548': 'ZLE (Kennedy)'}, ('MOCNY', '4950038')),
    ('Forum: Czarny Anioł. Opowieść o Ewie Demarczyk (E[224])', 'Czarny Anioł. Opowieść o Ewie Demarczyk',
     ['Angelika Kuźniak', 'Ewelina Karpacz-Oboładze'], {'193044': 'OK', '92996': 'ZLE (Connolly)'}, ('MOCNY', '193044')),
    ('Forum: Leonia (bez autora, E[195])', 'Leonia', None,
     {'80211': 'ok (Adler)', '4895467': 'ok (Menvielle)', '293693': 'ok (Wizytki)'}, ('MOCNY', '80211')),
]


class FakeLog(object):
    def __init__(self):
        self.lines = []
    def _add(self, lvl, *a):
        self.lines.append((lvl, ' '.join(str(x) for x in a)))
    def info(self, *a): self._add('INFO', *a)
    def debug(self, *a): self._add('DEBUG', *a)
    def warn(self, *a): self._add('WARN', *a)
    def warning(self, *a): self._add('WARN', *a)
    def error(self, *a): self._add('ERROR', *a)
    def exception(self, *a): self._add('EXC', *a)


class Abort(object):
    def is_set(self):
        return False


def set_config(**over):
    prefs = dict(cfg.DEFAULT_STORE_VALUES)
    for k, v in over.items():
        prefs[getattr(cfg, k)] = v
    cfg.plugin_prefs[cfg.STORE_NAME] = prefs


def make_plugin():
    p = lc_new.LubimyCzytac.__new__(lc_new.LubimyCzytac)
    p._identifier_to_cover_url_cache = {}
    p._isbn_to_identifier_cache = {}
    p.browser = None
    return p


def prepared(title, authors):
    """To samo, co robi identify() przed _search: usunięcie diakrytyków."""
    title = get_udc().decode(title) if title is not None else ''
    authors = [get_udc().decode(a) for a in authors] if authors else None
    return title, authors


def all_queries(p, log):
    urls = []
    for name, title, authors, _exp, _want in CASES:
        t, a = prepared(title, authors)
        for label, vt, va in p._query_variants(t, a):
            q = p.create_query(log, title=vt, authors=va)
            if q and q not in urls:
                urls.append(q)
    return urls


def render_results(cards):
    out = []
    for title, authors, href in cards:
        au = ''.join('<a href="/autor/1/x">%s</a>' % a for a in authors)
        out.append('<div class="book-card"><a class="book-card__title" href="%s">%s</a>'
                   '<div class="book-card__author">%s</div></div>' % (href, title, au))
    return '<html><head><meta charset="utf-8"></head><body><div id="ksiazki">%s</div></body></html>' % ''.join(out)


def run(recorded):
    p = make_plugin()
    set_config()
    missing = set()

    def fetch(log, br, query, timeout):
        if query not in recorded:
            missing.add(query)
            return None
        return lxml.html.fromstring(render_results(recorded[query]).encode('utf-8'))
    p._fetch_search_page = fetch

    summary = []
    failures = 0
    for name, title, authors, expect, (exp_kind, exp_first) in CASES:
        log = FakeLog()
        t, a = prepared(title, authors)
        authors_lc = list(a) if a else None
        cands = p._search(log, None, t, a, authors_lc, 30, Abort())
        ids = [re.search(r'/(?:ksiazka|audiobook)/(\d+)', c).group(1) for c in cands]
        tries = [l for _, l in log.lines if l.startswith('BECKY -- proba') or 'BECKY INFO: proba' in l or 'zaden wariant' in l or l == 'LAST']
        strong = any('zgodny z tytulem' in l for l in tries)
        kind = 'MOCNY' if strong else ('slaby' if cands else 'brak')
        first = ids[0] if ids else None
        passed = (kind == exp_kind and first == exp_first)
        if not passed:
            failures += 1
        verdicts = [expect.get(i, '?') for i in ids]
        print('\n=== %s  [%s]' % (name, 'PASS' if passed else 'FAIL: oczekiwano %s %s' % (exp_kind, exp_first)))
        print('    calibre: %r / %r' % (title, authors))
        for l in tries:
            print('    ' + l.replace('---\n', ''))
        for c, i, v in zip(cands, ids, verdicts):
            print('    -> %s  [%s]  %s' % (i, v, c))
        if not cands:
            print('    -> (brak kandydatow)')
        summary.append((name, kind, verdicts[0] if verdicts else '-', len(cands), passed))
    print('\n\n%-78s %-6s %s' % ('PRZYPADEK', 'WYNIK', 'PIERWSZY KANDYDAT'))
    for name, kind, first, n, passed in summary:
        print('%-78s %-6s %s (kandydatow: %d)%s' % (name[:78], kind, first, n, '' if passed else '   <-- FAIL'))
    if missing:
        print('\nBRAK NAGRAN dla %d zapytan:' % len(missing))
        for m in sorted(missing):
            print('  ' + m)
    print('\n%d przypadkow, %d niezgodnych z oczekiwaniem' % (len(CASES), failures))
    return failures


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'queries':
        p = make_plugin()
        set_config()
        print(json.dumps(all_queries(p, FakeLog()), ensure_ascii=False, indent=0))
    elif mode == 'run':
        with io.open(sys.argv[2], encoding='utf-8') as fh:
            recorded = json.load(fh)
        sys.exit(1 if run(recorded) else 0)
