# Pomysły na kolejne wersje

Zapis pomysłów, które nie weszły do 2.4.0. Każdy ma opis problemu, propozycję rozwiązania i orientacyjny koszt. Kolejność = priorytet.

## 1. Wybór wydania po tytule, gdy ISBN nic nie da

**Problem.** Opcja „Prefer matching ISBN” działa tylko wtedy, gdy LC zna ISBN wydania. Przykład z testów (2026-10-14): „Summoner Zaklinacz 1. Początek” (ISBN 9788376864204) – wtyczka trafiła właściwą książkę, ale wydanie „Początek” (273380, Jaguar 2015), podczas gdy wydanie „Summoner: Początek” (4889667) ma na LC ISBN `000000000000` i nie dało się go wskazać.

**Propozycja.** Gdy skan ISBN nie da dokładnego trafienia, wybrać spośród wydań to, którego tytuł najlepiej pokrywa się z tytułem z calibre – np. liczbą wspólnych tokenów po normalizacji (bez diakrytyków, małe litery, bez interpunkcji). „Summoner: Początek” ma dwa z czterech tokenów tytułu „Summoner Zaklinacz 1. Początek”, „Początek” – jeden. Przy remisie zostaje pierwotny wynik.

**Gdzie.** `worker.py`, obok `find_edition_by_isbn` – tytuły wydań są już odczytywane z listy `/ksiazka/wydania/<ID>`, więc ocena pokrycia nie wymaga dodatkowych żądań; trzeba pobrać tylko stronę wybranego wydania (jedno żądanie więcej).

**Koszt.** ~20–30 linii + scenariusz w testach. Uwaga: różnica między wydaniami bywa czysto edytorska (ten sam tytuł) – wtedy heurystyka niczego nie zmienia i to jest właściwe zachowanie.

## 2. Równoległe pobieranie stron wydań podczas skanu ISBN

**Problem.** `find_edition_by_isbn` pobiera strony wydań po kolei i kończy na pierwszym trafieniu. „Wszystko czerwone” Chmielewskiej ma 14 wydań; właściwe było dwunaste – całe pobranie trwało 7,3 s.

**Propozycja.** Niewielka pula wątków (3–4) pobierająca strony wydań równolegle, z przerwaniem reszty po pierwszym dokładnym trafieniu. Limit równoczesnych żądań zostawić mały, żeby nie obciążać LC i nie prowokować błędów 500/503, które serwis zwraca pod obciążeniem.

**Gdzie.** `worker.py`, `find_edition_by_isbn`. Ze względu na zgodność z calibre 3.48 (Python 2) nie ma `concurrent.futures` – użyć `threading.Thread` + `queue.Queue`, tak jak robi to już `identify()` z Workerami.

**Koszt.** ~40 linii. Przyspieszenie z ~7 s do ~2 s w najgorszym przypadku; przy 1–3 wydaniach bez różnicy.

## 3. Inne wydania i zmiana tytułu (badanie z 14.10.2026)

**Ustalenie.** Wyszukiwarka LC – strona wyników i podpowiedzi JSON (`/searcher/getsuggestions`, `/searcher/getSuggestedBook`) – indeksuje tylko wydanie główne każdej książki. Wydania o innym tytule („Król afer” i „Król pozwów” pod „Królem odszkodowań” 5001504, „Twarzyczka” 20677 pod „Buźką” 257761) są dla niej niewidoczne. Calibre nie przekazuje wtyczce wydawcy, więc przy tym samym tytule wtyczka zawsze zwróci wydanie główne; wydanie użytkownika wskazuje ISBN albo identyfikator `lubimyczytac:<ID>` (opisane w README).

**Zrobione w 2.4.1** (odtworzone kodem na nagraniach 81 zapytań, `tests/rare_cases.py`): dokładny tytuł przed częściowym („Cała prawda o planecie Ksi” → 111247, nie zbiór 4143); wydania zbiorcze (`;` w tytule, „KSIĄŻKI WYBRANE”) jako słabe; bez listy zapasowej `no_matches` (zamiast 4 losowych książek – brak wyników); normalizacja zer wiodących („#04” → „#4”); separator podtytułu tylko przy odstępie po kropce i nie po inicjale („cz.1”, „J.R.R.”).

**Do rozważenia dalej:**

1. **Poziom 1 – dopasowanie po tytule innego wydania** (osobna opcja w konfiguracji, domyślnie wyłączona): gdy żaden wariant nie dał wyniku mocnego, dla słabych kandydatów ze zgodnym autorem pobrać `/ksiazka/wydania/<ID>` i porównać tytuły wydań z tytułem z calibre; trafienie = wydanie użytkownika zamiast głównego. Koszt ≤ 4 żądania; kod obok `find_edition_by_isbn` / `parse_inne_wydania_all`. Działa, gdy wydanie główne pojawi się w wynikach dzięki autorowi („Dola Salem” → „Miasteczko Salem”); nie pomoże „Twarzyczce”, bo „Buźka” w ogóle nie wypada w wynikach tego zapytania.
2. **Poziom 2 – szukanie wśród książek autora** (druga osobna opcja, domyślnie wyłączona): zapytanie pełnym imieniem i nazwiskiem (`Sophie Hannah` → 10 książek na pierwszej stronie, „Buźka” 4.), potem listy wydań tych książek – „Twarzyczka” znaleziona jako 20677. 1 + do 10 żądań, z pulą wątków (pomysł nr 2) ok. 3–5 s. Nie pomoże płodnym autorom: „Król odszkodowań” jest 22. na liście 60+ książek Grishama (`/katalog/ksiazki?authors[]=19026`, 30 na stronę); dla Kinga podobnie.
3. **Wyszukiwarka internetowa jako ostatnia deska ratunku** (gałąź `LubimyCzytacGoogle`, 2017–2018). Strony wydań niegłównych są indeksowane przez wyszukiwarki: zapytanie `"Król pozwów" Grisham lubimyczytac` zwraca `lubimyczytac.pl/ksiazka/52298/krol-afer`. Problem jest po stronie dostępu: Google wymaga klucza Custom Search JSON API (100 zapytań dziennie za darmo) albo skrobania wyników, które kończy się CAPTCHA; alternatywą jest DuckDuckGo (`html.duckduckgo.com/html/?q=`), skrobany, ale bez klucza. Warto najpierw sprawdzić ręcznie na 10–20 tytułach z `tests/rare_cases.py`, ile wydań niegłównych da się tak znaleźć, i dopiero potem decydować o opcji.
4. **Podpowiedzi JSON LC** (gałąź `LubimyCzytacAjax`): `/searcher/getsuggestions?phrase=…` nadal działa i zwraca książki z `id`, `title`, `isbn`, `author`, `cycle`, `serie` – te same dane, co kafelki HTML, bez parsowania. Ten sam indeks, więc nie rozwiązuje problemu wydań, ale jest zapasowym źródłem wyników na wypadek kolejnej przebudowy HTML strony wyszukiwarki.
5. **Słabe dopasowanie tytułu, gdy tytuł LC jest krótszy** („Adwokat” pasuje do „Uliczny adwokat”, „Salem” do „Dola Salem”): po odsiewie autorów zostają książki innych autorów. Można wymagać, by krótszy tytuł miał ≥ 2 słowa albo ≥ połowę słów dłuższego – do sprawdzenia na nagraniach, czy nie gubi przypadków typu „Hobbit” vs „Hobbit, czyli tam i z powrotem”.

## 4. Drobiazgi do rozważenia

- **Nazwiska dwuliterowe** (En, Li, Xu, Mo). Filtr `len(tok) > 2` w `becky_get_author_tokens` odrzuca je razem z inicjałami, więc do zapytania jako „nazwisko” trafia imię (test „W objęciach namiętności”, Camilla En: zapytanie `Camilla W objeciach namietnosci` – LC i tak znalazło książkę). Przed zmianą sprawdzić na żywym LC, jak wyszukiwarka reaguje na dwuliterowe frazy.
- **`config_labels` w `identify()`** powiela listę kluczy konfiguracji – generować z `DEFAULT_STORE_VALUES`, trzymając etykiety obok kluczy w `config.py`.
- **Kolejność równorzędnych trafień przy wyłączonym „Fast matching”.** Każdy kolejny wynik zgodny z tytułem i autorem jest wstawiany na początek listy, więc ostatni wygrywa. Nieistotne przy domyślnym ustawieniu; przy sortowaniu końcowym i tak dominuje `MetadataCompareKeyGen`.
- **`isPartOfSeries` w JSON-LD.** Strony wydań e-bookowych (np. „Ciemny las” 4849940) mają cykl także w JSON-LD – potencjalnie stabilniejsze źródło niż XPath po `span/a[href*="/cykl/"]`.
- **Kafelek wyników LC pokazuje najwyżej dwóch autorów.** Rozwiązane częściowo odsiewem po pobraniu stron (`_filter_results_by_authors`); gdyby LC zmieniło układ kafelka, warto sprawdzić, czy nie pokazuje już wszystkich.
- **Testy w repozytorium (`tests/`).** Atrapy calibre, syntetyczna strona książki wzorowana na żywej, atrapa wyszukiwarki LC odtwarzająca zaobserwowane zachowania („Więzy krwi”, „The Naturals”, antologia), scenariusze `identify` – bez sieci, do uruchomienia w CI.
- **Po podniesieniu minimalnej wersji calibre do 5.0 (Python 3.8).** Usunąć shimy `six`/`polyglot`, `from __future__`, bloki try/except wokół importów `urllib`/`queue`/`html`; dopuścić f-stringi.
