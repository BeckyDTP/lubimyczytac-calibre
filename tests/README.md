# Testy bez calibre i bez sieci

Katalog pozwala przepuścić prawdziwy kod wtyczki (`_query_variants`, `create_query`,
`_search`, `_parse_search_results`) przez nagrane odpowiedzi wyszukiwarki LubimyCzytać.
Wyniki są powtarzalne, a jedna zmiana w dopasowywaniu tytułów od razu widać na 39 przypadkach.

```
tests/
  rare_cases.py     39 przypadków z oczekiwanym wynikiem; tryby `run` i `queries`
  test_hint.py      podpowiedź ręcznego wyszukania: wirtualny wynik tylko w oknie pobierania
  recorded.json     81 zapytań do LC z 2026-10-14: {adres: [[tytuł, [autorzy], href], ...]}
  harness/stubs/    atrapy calibre, polyglot, mechanize, qt – tylko to, czego używa wtyczka
```

Uruchomienie (Python 3 i pakiet `lxml`, w katalogu `tests/`):

```bash
python3 rare_cases.py run recorded.json   # przebieg _search na nagraniach, PASS/FAIL, kod wyjścia
python3 rare_cases.py queries             # adresy zapytań, które wysłałaby wtyczka
python3 test_hint.py                      # identify() z pustą stroną LC: kiedy pojawia się podpowiedź
```

Kod wtyczki jest ładowany wprost z katalogu nadrzędnego; inny katalog wskazuje zmienna
środowiskowa `LC_PLUGIN_DIR`.

## Jak czytać wyniki

Każdy przypadek ma oczekiwanie `(rodzaj, ID pierwszego kandydata)`: `MOCNY` – wynik zgodny
z tytułem i autorem, `slaby` – tylko tytuł albo tylko autor, `brak` – wtyczka nie zwraca nic.
Oceny przy identyfikatorach (`OK` – właściwe wydanie, `ok` – właściwa książka w innym wydaniu,
`ZLE` – inna książka) opisują, co użytkownik by zobaczył. Wiersze oznaczone w `CASES` jako
„znane ograniczenie” zapisują zachowanie przyjęte świadomie (np. wydanie zbiorcze jako słaba
rezerwa, gdy LC nie zna szukanego tytułu) – zmiana wyniku w takim wierszu to sygnał do analizy,
niekoniecznie błąd.

## Nowe nagrania i przypadki

1. Dopisz przypadek do `CASES` (nazwa, tytuł z calibre, autorzy z calibre, oceny ID, oczekiwanie).
2. `python3 rare_cases.py queries` wypisze adresy, których brakuje w nagraniach.
3. Dla każdego adresu zapisz w `recorded.json` listę kafelków `div#ksiazki div.book-card`
   (tytuł z `a.book-card__title`, autorzy z `div.book-card__author a`, `href` tytułu).
   Tryb `run` wypisuje na końcu adresy bez nagrania.

Testy integracyjne na żywym serwisie (lista `lctests` w `__init__.py`) uruchamia się nadal
przez `calibre-debug -e __init__.py` – patrz CONTRIBUTING.md.
