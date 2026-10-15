# Wtyczka LubimyCzytać do Calibre

Wtyczka źródła metadanych dla programu [Calibre](https://calibre-ebook.com/), pobierająca dane książek i okładki z serwisu [LubimyCzytać](https://lubimyczytac.pl/).

**Aktualna wersja źródeł:** 2.4.0  
**Minimalna wersja Calibre zadeklarowana w kodzie:** 3.48.0  
**Język dokumentacji i zgłoszeń:** polski

## Możliwości

Wtyczka może pobierać między innymi:

- autorów i tytuł;
- wydawcę i datę wydania;
- ISBN (zależnie od ustawień);
- serię i numer w serii;
- ocenę i liczbę ocen;
- gatunek lub słowa kluczowe jako etykiety;
- opis książki;
- język;
- okładkę.

Dodatkowe informacje mogą być dołączane do opisu zgodnie z ustawieniami wtyczki. Obejmują m.in. liczbę stron, tytuł oryginalny, tłumaczy, cykl wydawniczy, gatunek, słowa kluczowe, ocenę i liczbę ocen, identyfikator LubimyCzytać oraz daty pierwszego wydania. Wtyczka potrafi również informować o innych wydaniach książki i umieszczać ich listy w opisie.

Jednym z pierwotnych celów projektu było wyszukiwanie polskich książek mimo braku polskich znaków diakrytycznych w tytułach lub nazwiskach odczytanych z nazw plików.

## Instalacja

1. Pobierz plik ZIP z sekcji **Releases** tego repozytorium.
2. W Calibre otwórz **Preferencje → Wtyczki → Wczytaj wtyczkę z pliku**.
3. Wskaż pobrany plik ZIP i zaakceptuj instalację.
4. Jeśli Calibre poprosi o ponowne uruchomienie, uruchom program ponownie.

To wtyczka źródła metadanych, a nie wtyczka interfejsu. Nie należy oczekiwać osobnego przycisku na pasku narzędzi.

## Konfiguracja

Po instalacji ustawienia są dostępne w sekcji wtyczek źródeł metadanych. Wśród opcji znajdują się m.in.:

- limit wyników wyszukiwania do sprawdzenia;
- tryb szybkiego dopasowania;
- sposób dodawania gatunku lub słów kluczowych do etykiet;
- zastępowanie istniejącego ISBN;
- preferowanie wydania z dokładnie pasującym ISBN – opcja domyślnie wyłączona; lista wydań nie zawiera numerów ISBN, więc każde sprawdzane wydanie to osobne żądanie – wtyczka sprawdza najpierw wydania o tym samym tytule i kończy po 20 stronach albo 60 sekundach, zostawiając pierwotny wynik;
- obsługa sytuacji, w których wewnętrzna wyszukiwarka serwisu działa nieprawidłowo;
- podpowiedź ręcznego wyszukania, gdy LubimyCzytać nie zna tytułu (wirtualny wynik z linkami; tylko w oknie pojedynczego pobierania) – opcja domyślnie wyłączona;
- wybór dodatkowych informacji dołączanych do opisu, w tym informacji o innych wydaniach.

Dostępne opcje i ich działanie mogą zmieniać się wraz z kolejnymi wersjami wtyczki.

### Jak wskazać konkretne wydanie

Wyszukiwarka LubimyCzytać zna tylko wydanie główne każdej książki, a calibre nie przekazuje wtyczce wydawcy. Dlatego przy kilku wydaniach tego samego tytułu wtyczka zwraca wydanie główne (zwykle najnowsze), a książki wydanej wcześniej pod innym tytułem po samym tytule nie znajdzie. Są dwa sposoby, by dostać dokładnie to wydanie, które masz na półce:

- wpisz w calibre ISBN tego wydania i włącz opcję **Prefer matching ISBN** – wtyczka przejrzy listę wydań znalezionej książki i wybierze to z pasującym ISBN (o ile LubimyCzytać zna ten numer);
- wpisz identyfikator `lubimyczytac:<ID>` w polu identyfikatorów książki (ID to liczba z adresu strony wydania, np. `lubimyczytac:74063` dla `lubimyczytac.pl/ksiazka/74063/krol-pozwow`) i pobierz metadane ponownie – wtyczka pominie wyszukiwarkę i pobierze wskazaną stronę.

Strony wydań wydanych pod innym tytułem są indeksowane przez wyszukiwarki internetowe, choć wyszukiwarka LubimyCzytać ich nie zwraca. Opcja **Suggest a manual search when nothing is found** dodaje w takiej sytuacji do okna wyników wirtualny wynik (ten sam tytuł i autor, czerwone ostrzeżenie w opisie, bez identyfikatora LC) z gotowymi linkami do wyszukania w Google i DuckDuckGo zawężonego do `lubimyczytac.pl`, do wyszukiwarki LC oraz z instrukcją wpisania identyfikatora. Wynik pojawia się wyłącznie w oknie pobierania metadanych dla jednej książki – w pobieraniu masowym calibre zastosowałoby go bez pytania, dlatego wtyczka rozpoznaje tryb i w masowym podpowiedzi nie dodaje. Jeśli korzystasz z masowego pobierania z LC, zostaw tę opcję wyłączoną.

## Zgłaszanie błędów i propozycji

Zgłoszenia przyjmujemy po polsku w sekcji **Issues** repozytorium.

W zgłoszeniu błędu podaj, jeśli to możliwe:

- wersję Calibre i wtyczki;
- system operacyjny;
- tytuł i autora książki, na której występuje problem;
- oczekiwany i faktyczny rezultat;
- kroki pozwalające odtworzyć problem;
- odpowiedni fragment logu pobierania metadanych.

Przed opublikowaniem logu usuń dane prywatne. Zgłaszając problem z konkretną książką, podaj publiczny adres jej strony w LubimyCzytać, jeśli jest dostępny.

## Diagnostyka

Najwięcej o działaniu wtyczki mówi dziennik pobierania metadanych, dostępny w oknie pobierania metadanych calibre po zakończeniu wyszukiwania. Wtyczka zapisuje w nim:

- aktualną konfigurację (ułatwia odtworzenie problemu u innej osoby);
- tryb pobierania rozpoznany przez wtyczkę (`tryb pobierania: single` – okno pojedynczej książki, `bulk` – pobieranie masowe, `unknown` – nie rozpoznano, np. w testach `calibre-debug`);
- kolejne warianty zapytań do wyszukiwarki LubimyCzytać (`BECKY -- proba 1/5: autor + pelny tytul`) i powód przejścia do następnego;
- ocenę każdego wyniku z listy (zgodność tytułu, autora, autora ukrytego) oraz kandydatów odrzuconych po pobraniu ich stron;
- wskazówki `BECKY HINT`, gdy wtyczka celowo zrobiła coś inaczej niż zwykle.

Szczegółowy raport parsowania – skąd dokładnie (JSON-LD, znaczniki `meta`, XPath) pobrano każde pole i które źródła zawiodły – włącza zmienna środowiskowa `LUBIMYCZYTAC_DEBUG=1`. Nie trzeba niczego zmieniać w kodzie:

```bat
:: Windows (cmd)
set LUBIMYCZYTAC_DEBUG=1
calibre-debug -g
```

```bash
# Linux / macOS
LUBIMYCZYTAC_DEBUG=1 calibre-debug -g
```

Jedno pobieranie metadanych ma limit 150 sekund: po jego przekroczeniu wtyczka nie wysyła kolejnych zapytań i zwraca to, co zdążyła pobrać, razem z dziennikiem (wpis `limit czasu ... przekroczony`). Calibre zabija proces pobierania po 300 sekundach i wtedy dziennik ginie – stąd limit wtyczki jest krótszy.

Przy ustawionej zmiennej `LUBIMYCZYTAC_DEBUG=1` cały dziennik pobierania jest dodatkowo dopisywany do pliku `plugins/lubimyczytac-debug.log` w katalogu konfiguracji calibre (Preferencje → Różne → „Otwórz katalog konfiguracji calibre”). Przydaje się, gdy calibre przerwie zbyt długie pobieranie i nie pokaże dziennika; po przekroczeniu 5 MB plik jest zaczynany od nowa.

Komunikaty logu są celowo pisane bez polskich znaków diakrytycznych, żeby czytały się tak samo w każdej konsoli i dało się je bez obaw wklejać do zgłoszeń.

## Budowanie paczki instalacyjnej

Do zbudowania ZIP-a potrzebny jest Python 3; skrypt korzysta wyłącznie ze standardowej biblioteki Pythona. Nie trzeba instalować Calibre ani dodatkowych pakietów.

W katalogu repozytorium uruchom:

```bash
python build.py
```

W systemie, w którym polecenie `python` wskazuje inną wersję, użyj odpowiedniego polecenia, np. `python3` albo `py -3`.

Gotowy plik pojawi się w katalogu `dist/`, np. `dist/LubimyCzytac-2.4.0.zip`. Skrypt korzysta z jawnej listy plików, sprawdza obecność wymaganych zasobów i weryfikuje zawartość utworzonego archiwum. Pliki dokumentacji, kod budujący i katalog `.git` nie trafiają do paczki instalacyjnej.

## Zgodność z calibre i plany

- Kod deklaruje minimalną wersję **calibre 3.48**. Calibre 3.x i 4.x działało jeszcze na Pythonie 2.7 (Python 3 pojawił się w calibre 5.0), dlatego źródła są pisane tak, by działały jednocześnie w Pythonie 2.7 i 3.x: bez f-stringów, z warstwą zgodności (`six`, `polyglot`, importy przez `try/except`).
- Wersja 2.4.0 była testowana w calibre 9.16 (Windows).
- Plan: następne duże wydanie podniesie minimalną wersję do **calibre 5.0 (Python 3.8)**; kolejne kroki to calibre 6 (Python 3.10) i calibre 7 (Python 3.11). Przy tej okazji znikną shimy zgodności – lista jest w [`ideas.md`](ideas.md).

Pomysły na kolejne wersje, które nie weszły do bieżącego wydania, zbieramy w pliku [`ideas.md`](ideas.md).

## Historia projektu

Wtyczka powstała w 2011 roku. Jej autorem był **Jacek Bieńkowski** (`jbienko`), który stworzył ją z myślą o wyszukiwaniu polskich książek z uwzględnieniem polskich znaków diakrytycznych. Wersja 0.5.0 ukazała się **28 sierpnia 2011 roku**.

W późniejszym okresie serwis LubimyCzytać przeszedł znaczącą przebudowę układu stron, wskutek czego wersja 0.5.6 przestała pobierać dane. **Roman Cupisz** przygotował gruntownie przebudowaną wersję 2.0.0, która dostosowywała wtyczkę do zmian serwisu i wprowadzała zgodność z Calibre 2.0.

Przy wersji 2.0.1 pojawiły się dwie niezależne linie rozwoju. **Szemkiel** przygotował równoległą poprawkę do wersji 2.0.0 Romana Cupisza. **Becky** rozpoczęła własną linię rozwoju, kontynuowaną w kolejnych latach. Nie są znane późniejsze wydania linii Szemkiela.

Obecna wersja wtyczki jest wynikiem wieloletniego utrzymania i rozwijania projektu, dostosowywania go do zmian serwisu LubimyCzytać oraz kolejnych wersji Calibre, przy zachowaniu ciągłości z pracą wcześniejszych autorów.

## Autorstwo i licencja

Kod historycznych wersji wskazuje autorstwo Jacka Bieńkowskiego (2011) oraz Romana Cupisza (2014). Nagłówki obecnego kodu odnotowują również wkład Becky w latach 2015–2026.

Projekt jest udostępniany na warunkach GNU General Public License, wersja 3. Szczegóły znajdują się w pliku [`LICENSE`](LICENSE). Informacje o autorach zachowano w kodzie i w historii projektu.

## Struktura repozytorium

- `__init__.py`, `worker.py`, `config.py` – kod wtyczki (`__init__.py` zawiera też wbudowane testy: `calibre-debug -e __init__.py`);
- `plugin-import-name-lubimyczytac.txt` – nazwa modułu importu wymagana przez calibre;
- `images/` – ikona wtyczki;
- `translations/` – szablon tłumaczeń `default.po`, robocze `pl.po` i `cs.po` oraz skompilowane `pl.mo` i `cs.mo`;
- `CHANGELOG.md` – historia zmian (po angielsku, bo te same notatki trafiają na forum MobileRead);
- `changelog.txt` – ta sama historia w formacie BBCode, do wklejenia w wątku na MobileRead;
- `ideas.md` – pomysły na kolejne wersje;
- `tests/` – testy wyszukiwania na nagranych odpowiedziach LubimyCzytać, bez calibre i bez sieci (`python3 tests/rare_cases.py run tests/recorded.json`);
- `build.py` – budowanie paczki instalacyjnej do `dist/` (katalog ignorowany przez git);
- `CONTRIBUTING.md` – zasady zgłaszania błędów i zmian w kodzie;
- `.github/ISSUE_TEMPLATE/` – formularze zgłoszeń;
- `.github/workflows/release.yml` – automatyczne budowanie i publikowanie paczki po wypchnięciu tagu `v*`.
