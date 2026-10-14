# Współtworzenie projektu

Zgłoszenia i opisy problemów najlepiej przygotowywać po polsku.

## Zgłaszanie błędów

Przed utworzeniem zgłoszenia:

1. sprawdź, czy podobny problem nie został już zgłoszony;
2. upewnij się, że korzystasz z aktualnej wersji wtyczki dostępnej w Releases;
3. przygotuj możliwie mały przykład pozwalający odtworzyć problem.

Podaj wersję Calibre, wersję wtyczki, system operacyjny, kroki odtworzenia i rezultat oczekiwany oraz rzeczywisty. W przypadku błędów pobierania metadanych dołącz odpowiedni log. Przed publikacją usuń z niego dane prywatne.

## Propozycje zmian

Opisz problem, który proponowana zmiana rozwiązuje, i jej oczekiwane zachowanie. Jeśli to możliwe, rozważ przypadki brzegowe, zmiany w strukturze stron LubimyCzytać oraz zgodność ze wspieraną przez kod wersją Calibre.

## Zmiany w kodzie

- Zachowuj istniejące informacje o autorach i licencji.
- Nie dołączaj do paczki instalacyjnej dokumentacji, plików tymczasowych ani katalogów narzędzi programistycznych.
- Po zmianie kodu uruchom `python build.py` i sprawdź, czy paczka powstaje poprawnie.
- Nie deklaruj, że problem został rozwiązany, jeśli nie został zweryfikowany w praktyce.

## Konwencje kodu

- **Zgodność.** Kod musi działać w calibre 3.48 (Python 2.7) i w aktualnym calibre (Python 3.x). Bez f-stringów i składni dostępnej tylko w Pythonie 3; tekst to `unicode` (`six.text_type`), importy zależne od wersji przez `try/except` albo `polyglot`. Przed wysłaniem zmiany sprawdź, czy plik nadal kompiluje się w Pythonie 2 (`python2 -m py_compile worker.py`), jeśli masz go pod ręką.
- **Komentarze i docstringi po polsku.** Każda funkcja ma docstring: co robi, co przyjmuje, co zwraca. Komentarz ma tłumaczyć *dlaczego*, a nie powtarzać kod.
- **Komunikaty w logu** `identify` piszemy bez polskich znaków (ASCII) i z prefiksem `BECKY` / `BECKY INFO` / `BECKY HINT`, żeby dało się je łatwo filtrować i wklejać do zgłoszeń.
- **Nowe pola i źródła danych.** Najpierw JSON-LD (`get_jsonld_data`) albo znaczniki `meta`, dopiero potem XPath po HTML jako zapas. Każdą próbę odnotuj przez `record_parse_attempt`, żeby trafiła do raportu `LUBIMYCZYTAC_DEBUG`.
- **Teksty interfejsu** (`config.py`, `__init__.py`) opakuj w `_()` i dodaj do `translations/default.po`; potem odśwież `pl.po` / `cs.po` (Poedit) i skompiluj `.mo`. Do paczki trafiają wyłącznie pliki `.mo` (lista w `build.py`).
- **Każdą zmianę opisz w `CHANGELOG.md`** (po angielsku, z prefiksem `Added:` / `Changed:` / `Fixed:` / `Removed:`), a przy wydaniu podnieś `PLUGINVER` w `__init__.py`. Tag wydania ma postać `v<wersja>` i musi zgadzać się z `PLUGINVER` – workflow to sprawdza.

## Testy

Wtyczka ma wbudowane testy w `__init__.py`. Uruchamia się je przez `calibre-debug`, który **korzysta z wtyczki zainstalowanej w calibre**, a nie z plików w katalogu roboczym. Dlatego kolejność jest ważna:

1. Zbuduj paczkę: `python build.py`.
2. Zainstaluj ją w calibre (**Preferencje → Wtyczki → Wczytaj wtyczkę z pliku**) i zrestartuj calibre, jeśli o to poprosi.
3. W katalogu repozytorium uruchom:

   ```bash
   calibre-debug -e __init__.py
   ```

   Najpierw wykonują się szybkie testy jednostkowe funkcji pomocniczych (`HelperTests`, bez sieci), potem testy integracyjne `test_identify_plugin`, które łączą się z lubimyczytac.pl i sprawdzają konkretne książki z listy `lctests`.

4. Wygodne przekierowanie logów do plików: `calibre-debug -e __init__.py 2>lclog2.txt >lclog1.txt`. Szczegółowy raport parsowania włączysz zmienną `LUBIMYCZYTAC_DEBUG=1`.
5. Zmiany w dopasowywaniu tytułów i autorów sprawdź też bez calibre: `python3 tests/rare_cases.py run tests/recorded.json` odtwarza wyszukiwanie na 39 nagranych przypadkach i kończy się kodem błędu, gdy wynik odbiega od oczekiwanego (opis w `tests/README.md`).

Poprawiając wyszukiwanie dla konkretnej książki, dopisz ją do `lctests` (tytuł, autor, oczekiwany identyfikator LC). Testy integracyjne zależą od żywego serwisu, więc pojedyncze niepowodzenie warto najpierw sprawdzić ręcznie w przeglądarce, zanim uznasz je za błąd wtyczki.
