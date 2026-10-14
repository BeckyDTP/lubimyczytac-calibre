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

## 3. Drobiazgi do rozważenia

- **Nazwiska dwuliterowe** (En, Li, Xu, Mo). Filtr `len(tok) > 2` w `becky_get_author_tokens` odrzuca je razem z inicjałami, więc do zapytania jako „nazwisko” trafia imię (test „W objęciach namiętności”, Camilla En: zapytanie `Camilla W objeciach namietnosci` – LC i tak znalazło książkę). Przed zmianą sprawdzić na żywym LC, jak wyszukiwarka reaguje na dwuliterowe frazy.
- **`config_labels` w `identify()`** powiela listę kluczy konfiguracji – generować z `DEFAULT_STORE_VALUES`, trzymając etykiety obok kluczy w `config.py`.
- **Kolejność równorzędnych trafień przy wyłączonym „Fast matching”.** Każdy kolejny wynik zgodny z tytułem i autorem jest wstawiany na początek listy, więc ostatni wygrywa. Nieistotne przy domyślnym ustawieniu; przy sortowaniu końcowym i tak dominuje `MetadataCompareKeyGen`.
- **`isPartOfSeries` w JSON-LD.** Strony wydań e-bookowych (np. „Ciemny las” 4849940) mają cykl także w JSON-LD – potencjalnie stabilniejsze źródło niż XPath po `span/a[href*="/cykl/"]`.
- **Kafelek wyników LC pokazuje najwyżej dwóch autorów.** Rozwiązane częściowo odsiewem po pobraniu stron (`_filter_results_by_authors`); gdyby LC zmieniło układ kafelka, warto sprawdzić, czy nie pokazuje już wszystkich.
- **Testy w repozytorium (`tests/`).** Atrapy calibre, syntetyczna strona książki wzorowana na żywej, atrapa wyszukiwarki LC odtwarzająca zaobserwowane zachowania („Więzy krwi”, „The Naturals”, antologia), scenariusze `identify` – bez sieci, do uruchomienia w CI.
- **Po podniesieniu minimalnej wersji calibre do 5.0 (Python 3.8).** Usunąć shimy `six`/`polyglot`, `from __future__`, bloki try/except wokół importów `urllib`/`queue`/`html`; dopuścić f-stringi.
