# Historia zmian

Wpisy są po angielsku, bo te same notatki publikujemy w wątku wtyczki na forum MobileRead. Najnowsza wersja na górze.

## Wersja 2.4.1 – 15 Oct 2026
*Wydanie przygotowane przez Becky.*
- Fixed: An exact title match now takes precedence over a partial one regardless of the order on the LubimyCzytac results page. 'Cała prawda o planecie Ksi' no longer resolves to the collection 'Cała prawda o planecie Ksi. Drugie spojrzenie na planetę Ksi', which LubimyCzytac lists first.
- Changed: Collected editions (titles listing several works separated by semicolons, or 'KSIĄŻKI WYBRANE: ...') that merely contain the searched title are treated as weak candidates instead of strong matches, so they no longer end the search with 'Fast matching'.
- Changed: Results matching neither the title nor the author are no longer returned as a last resort. When LubimyCzytac does not know the title at all, the plugin reports no results instead of four random books (and skips four page downloads).
- Fixed: Leading zeros in numbers no longer break title matching ('Moje szczęśliwe małżeństwo #04' in calibre vs '#4' on LubimyCzytac).
- Fixed: A dot inside an abbreviation or initials ('cz.1', 'J.R.R.', 'Philip K. Dick') is no longer treated as a subtitle separator; it used to produce pointless extra queries such as 'Hobb 1'.
- Changed: With 'Fast matching' disabled, candidates are ordered: exact title, partial title, weak matches. Previously the last strong match found ended up first.
- Added: Two search-based cases in the built-in tests (calibre-debug -e __init__.py): 'Cała prawda o planecie Ksi' and 'Moje szczęśliwe małżeństwo #04'.

## Wersja 2.4.0 – 14 Oct 2026
*Wydanie przygotowane przez Becky.*
- Added: The optional 'Prefer matching ISBN' setting (disabled by default). When enabled and calibre supplies an ISBN, the plugin looks for an exact ISBN match among the editions of the initially selected book and switches to that edition; otherwise the original result is kept. The check stops at the first exact match and is skipped when the initially selected edition already matches.
- Added: The diagnostic parsing report can be enabled with the LUBIMYCZYTAC_DEBUG=1 environment variable, without editing the code.
- Changed: Search strategy rewritten. The plugin tries several query variants in turn (author + full title, author + title before/after the separator, title only) and stops at the first result matching both title and author; a result matching only the title no longer ends the search. This covers titles like 'Series. Title', where LubimyCzytac lists only the part after the dot as the title.
- Changed: Author matching also accepts a matching surname (initials written differently in calibre and LC, e.g. 'J. R. R. Tolkien' vs 'J.R.R. Tolkien') and now works with the 'Last Name First Name' option.
- Changed: After the candidate pages are downloaded, candidates whose full author list does not contain the author from calibre are dropped. The search results page shows at most two authors, so anthologies used to produce several candidates.
- Changed: Search candidates keep their relevance order instead of being sorted alphabetically by URL.
- Changed: Lists of other editions: the full list is parsed more reliably, the short list is built from the actual titles instead of URL slugs, keeps Polish diacritics and merges duplicates differing only by HTML entities or spacing.
- Changed: The effective plugin configuration is written to the identify log to simplify diagnosis of user-specific issues.
- Changed: Code clean-up before publishing on GitHub: Polish docstrings and comments, dead code and leftovers removed.
- Changed: Updated the Polish and Czech translations.
- Fixed: Number of pages and rating count were never appended to the comment (wrong use of JSON-LD data). The publication date is now read from JSON-LD with an HTML fallback; the number of pages also falls back to the HTML details.
- Fixed: The 'Date of the first publication' option could not be saved independently of the Polish edition date.
- Fixed: Search results were parsed three times per book (the XPath also matched inner elements of the book card).
- Fixed: Compatibility with calibre 3.48 (f-string syntax in worker.py).
- Fixed: Improved error handling and handling of edge cases.
- Removed: Remaining code of the 'select other editions' dialog (calibre 9 forbids dialogs in metadata plugins) and the 'Dark theme' option.

## Wersja 2.3.13 – 22 Sep 2026
*Wydanie przygotowane przez Becky.*
- Fixed: A better-designed matching function for authors and book titles (thanks to @PiotrK for the suggestion)
- Changed: ISBN replacement is disabled by default (thanks to @PiotrK for the suggestion)

## Wersja 2.3.12 – 24 Aug 2026
*Wydanie przygotowane przez Becky.*
- Fixed: Metadata parsing failure (title, rating count, page count, publication date) for books where LC's JSON-LD contains raw control characters in review text, violating the JSON spec

## Wersja 2.3.11 – 2 Jun 2026
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the authors for audiobooks
- Fixed: Parsing clean titles for audiobooks
- Fixed: Downloading covers for audiobooks

## Wersja 2.3.10 – 29 May 2026
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the authors again

## Wersja 2.3.9 – 25 May 2026
*Poprawka: Pan Sosin.*
- Fixed: Parsing the authors after changes in lubimyczytac.pl HTML structure

## Wersja 2.3.8 – 16 Apr 2026
*Wydanie przygotowane przez Becky.*
- Fixed: Short descriptions download
- Removed: Option for select other editions

## Wersja 2.3.7 – 22 Oct 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Error handling while retrieving the publication date
- Fixed: Error handling while retrieving the rating count

## Wersja 2.3.6 – 21 Oct 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Error handling while retrieving the number of pages

## Wersja 2.3.5 – 26 Aug 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Error handling while retrieving ISBN
- Fixed: Improved downloading of the publication date of the book, again.
- Fixed: Cleaning the title if it also contains author data

## Wersja 2.3.4 – 26 Jun 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Publisher download

## Wersja 2.3.3 – 17 Mar 2025
*Wydanie przygotowane przez Becky.*
- New: Added support for audiobooks [beta].

## Wersja 2.3.2 – 19 Feb 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Another attempt to control error number 500

## Wersja 2.3.1 – 18 Feb 2025
*Wydanie przygotowane przez Becky.*
- Fixed: Attempting to download data despite error number 500

## Wersja 2.3.0 – 30 Nov 2024
*Wydanie przygotowane przez Becky.*
- New: Additional checkbox in the configuration that can be used when the internal search engine on the LC site does not work properly
- New: Ability to use a simplified form of page count for easier parsing of comments with other tools

## Wersja 2.2.35 – 24 Oct 2024
*Wydanie przygotowane przez Becky.*
- Changed: I am temporarily disabling the default search for author and title due to changes to the search engine on the LC site

## Wersja 2.2.34 – 17 Oct 2023
*Wydanie przygotowane przez Becky.*
- Changed: Adjustment of the number of pages in the commentary to the new METAmover plugin standard

## Wersja 2.2.33 – 2 Oct 2023
*Wydanie przygotowane przez Becky.*
- Added: Czech translation (by seeder)

## Wersja 2.2.32 – 3 Jul 2023
*Wydanie przygotowane przez Becky.*
- Fixed: Up version

## Wersja 2.2.31 – 26 Jun 2023
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing tags

## Wersja 2.2.30 – 27 Apr 2023
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing rating count

## Wersja 2.2.29 – 14 Nov 2022
*Wydanie przygotowane przez Becky.*
- Fixed: A rare case of a temporary problem with a book's page on the site

## Wersja 2.2.28 – 4 Aug 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Rare cases with a hash in the title

## Wersja 2.2.27 – 17 Jun 2022
*Wydanie przygotowane przez Becky.*
- Changed: MacOS only - ignore option for select other editions

## Wersja 2.2.26 – 14 May 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Quick fix

## Wersja 2.2.25 – 14 May 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the authors after changes in lubimyczytac.pl HTML structure

## Wersja 2.2.24 – 15 Mar 2022
*Wydanie przygotowane przez Becky.*
- Changed: Linux only - ignore option for select other editions

## Wersja 2.2.23 – 12 Feb 2022
*Wydanie przygotowane przez Becky.*
- Changed: Debian only - ignore option for select other editions

## Wersja 2.2.22 – 10 Feb 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Another way to solve the problem of different apostrophes in titles

## Wersja 2.2.21 – 8 Feb 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Minor bug while analyzing the search results

## Wersja 2.2.20 – 5 Feb 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Rare cases with an ampersand in the title
- Fixed: Rare cases with a slash in the title

## Wersja 2.2.19 – 2 Feb 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Better search for books that have an extra hyphen in the title

## Wersja 2.2.18 – 1 Feb 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Another solution for straight quotation marks
- Fixed: Fetching metadata for existing identifiers in calibre 3.48

## Wersja 2.2.17 – 28 Jan 2022
*Wydanie przygotowane przez Becky.*
- Changed: Improved fast matching algorithm when an LC site has a temporarily broken search engine

## Wersja 2.2.16 – 27 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fix: Lists of other editions (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 2.2.15 – 27 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fix: Restored functionality in calibre 3.48 (again)

## Wersja 2.2.14 – 27 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Translation

## Wersja 2.2.13 – 27 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Restored functionality in calibre 3.48

## Wersja 2.2.12 – 26 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Finding books with an incorrect (straight) apostrophe in the title

## Wersja 2.2.11 – 9 Jan 2022
*Wydanie przygotowane przez Becky.*
- Changed: Option that allows you to choose a dark theme

## Wersja 2.2.10 – 6 Jan 2022
*Wydanie przygotowane przez Becky.*
- Fixed: Error handling while retrieving the number of pages
- Fixed: The title of the current edition is not truncated
- Changed: Forcing a dark theme in the book edition selection window

## Wersja 2.2.9 – 1 Jan 2022
*Wydanie przygotowane przez Becky.*
- Change: Make compatible with upcoming calibre 6/Qt6
- New: The plugin version has been added in the configuration window

## Wersja 2.2.8 – 21 Dec 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Search for books that do not have an author specified

## Wersja 2.2.7 – 12 Dec 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the authors with "von", "van" or double-barrelled names
- New: Function override that determines the final order in the result list

## Wersja 2.2.6 – 12 Sep 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the title after changes in lubimyczytac.pl HTML structure

## Wersja 2.2.5 – 18 Aug 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the number of ratings

## Wersja 2.2.4 – 30 Jul 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing the number of pages

## Wersja 2.2.3 – 30 Jun 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Disable fast matching if selected list other editions in config

## Wersja 2.2.2 – 1 Jun 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Change of the cleanup function of the list for backward compatibility

## Wersja 2.2.1 – 1 Jun 2021
*Wydanie przygotowane przez Becky.*
- Fixed: Remove the brackets from the title, leaving the contents

## Wersja 2.2.0 – 28 May 2021
*Wydanie przygotowane przez Becky.*
- Changed: Parsing title + authors
- Fixed: Parsing empty date publication
- Fixed: List of other editions during metadata bulk download
- Fixed: Missing Polish translation

## Wersja 2.1.7 – 8 May 2021
*Wydanie przygotowane przez Becky.*
- Changed: With the surname before the first name option enabled, this convention also applies when saving metadata.

## Wersja 2.1.6 – 6 May 2021
*Wydanie przygotowane przez Becky.*
- Changed: Better parsing when a valid query returns no results

## Wersja 2.1.5 – 5 May 2021
*Wydanie przygotowane przez Becky.*
- Added: Added option for users who use "Last Name First Name" for authors

## Wersja 2.1.4 – 21 Dec 2020
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing ISBN number

## Wersja 2.1.3 – 28 Nov 2020
*Wydanie przygotowane przez Becky.*
- Added: Date of the first edition of the book
- Added: Date of the first edition of the book in Poland

## Wersja 2.1.2 – 18 Nov 2020
*Wydanie przygotowane przez Becky.*
- Changed: Error handling

## Wersja 2.1.1 – 16 Nov 2020
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing books without authors

## Wersja 2.1.0 – 15 Nov 2020
*Wydanie przygotowane przez Becky.*
- New: If the LC identifier is known, another edition can be selected.
- Changed: Better handle duplicate matches
- Changed: Better handle duplicate entries for other releases

## Wersja 2.0.46 – 21 Oct 2020
*Wydanie przygotowane przez Becky.*
- Fixed: Removing an endless loop when a book is not available on the LC website
- Fixed: Parsing other editions

## Wersja 2.0.45 – 25 Sep 2020
*Wydanie przygotowane przez Becky.*
- New: Added support for the number of people who rated the book
- Fixed: lxml bug which occurred in some cases

## Wersja 2.0.44 – 22 Apr 2020
*Wydanie przygotowane przez Becky.*
- Private build

## Wersja 2.0.43 – 4 Apr 2020
*Wydanie przygotowane przez Becky.*
- Changed: Improved search
- Private build

## Wersja 2.0.42 – 2 Apr 2020
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing authors

## Wersja 2.0.41 – 25 Mar 2020
*Wydanie przygotowane przez Becky.*
- Fixed: Parsing series (Cykl)

## Wersja 2.0.40 – 9 Jan 2020
*Wydanie przygotowane przez Becky.*
- Changed: More changes for Python 3 support in calibre.
- Minor fixes

## Wersja 2.0.39 – 7 Jan 2020
*Wydanie przygotowane przez Becky.*
- Changed: Changes for Python 3 support in calibre.

## Wersja 2.0.38 – 15 Nov 2019
*Wydanie przygotowane przez Becky.*
- Fixed: Special case -- slash in title

## Wersja 2.0.37 – 05 Nov 2019
*Wydanie przygotowane przez Becky.*
- Fixed: Fetching data for books with many co-authors

## Wersja 2.0.36 – 05 Nov 2019
*Wydanie przygotowane przez Becky.*
- Changed: Simplifying the search
- Fixed: Faster response in the absence of results

## Wersja 2.0.35 – 30 Oct 2019
*Wydanie przygotowane przez Becky.*
- Fixed: LC rating in numerical form

## Wersja 2.0.34 – 29 Oct 2019
*Wydanie przygotowane przez Becky.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 2.0.33 – 1 Jan 2019
*Wydanie przygotowane przez Becky.*
- Private build

## Wersja 2.0.32 – 11 Nov 2018
*Wydanie przygotowane przez Becky.*
- New: Add id_from_url for pasting URL and getting an identifier
- New: Option to "Fast matching"
- New: Strip diacritics in log file

## Wersja 2.0.31 – 11 Sep 2018
*Wydanie przygotowane przez Becky.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 2.0.30 – 27 Aug 2018
*Wydanie przygotowane przez Becky.*
- Fixed: Improved downloading of the publication date of the book.

## Wersja 2.0.29 – 17 Aug 2018
*Wydanie przygotowane przez Becky.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 2.0.28 – 13 Jan 2018
*Wydanie przygotowane przez Becky.*
- Changed: Improved parsing series

## Wersja 2.0.27 – 24 Sep 2017
*Wydanie przygotowane przez Becky.*
- Changed: Improved identification of books

## Wersja 2.0.26 – 10 Sep 2017
*Wydanie przygotowane przez Becky.*
- Fixed: Error handling for books without rating

## Wersja 2.0.25 – 10 Jul 2017
*Wydanie przygotowane przez Becky.*
- Added: Option to append LC rating in numerical form at the end of the comment

## Wersja 2.0.24.2 – 23 May 2017
*Wydanie przygotowane przez Becky.*
- Fixed: typo in translation

## Wersja 2.0.24.1 – 5 Apr 2017
*Wydanie przygotowane przez Becky.*
- Fixed: improved identify

## Wersja 2.0.24 – 24 Mar 2017
*Wydanie przygotowane przez Becky.*
- Changed: Priority for books with matched both: title and author.

## Wersja 2.0.23 – 23 Feb 2017
*Wydanie przygotowane przez Becky.*
- Changed: Parsing genres from LC
- Fixed: regression in 2.0.17-2.0.22 that spoil download Keywords as Tags
- Fixed: Better recognition of books for authors' names containing foreign diacritics
- Minor fixes

## Wersja 2.0.22 – 15 Feb 2017
*Wydanie przygotowane przez Becky.*
- Minor fixes

## Wersja 2.0.21 – 14 Feb 2017
*Wydanie przygotowane przez Becky.*
- Added: Option to append LC ID at the end of the comment
- Minor fixes

## Wersja 2.0.20 – 12 Feb 2017
*Wydanie przygotowane przez Becky.*
- Fixed: Improved translations
- Minor fixes

## Wersja 2.0.19 – 9 Feb 2017
*Wydanie przygotowane przez Becky.*
- Added: Option to append short list the other editions (without duplicate titles)
- Added: Option to append horizontal line after the other editions (before comment)
- Removed: Option to save the number of pages as additional identifier

## Wersja 2.0.18 – 6 Feb 2017
*Wydanie przygotowane przez Becky.*
- Added: Two options to append information about other editions at the begin of the comment

## Wersja 2.0.17 – 5 Feb 2017
*Wydanie przygotowane przez Becky.*
- Added: Option to append original title at the end of the comment
- Added: Option to append translators at the end of the comment
- Added: Option to append book series at the end of the comment
- Added: Option to append genre (kategoria) at the end of the comment
- Added: Option to append keywords at the end of the comment

## Wersja 2.0.16 – 29 Jan 2017
*Wydanie przygotowane przez Becky.*
- Fixed: Cover parsing (after changes in HTTP HEAD for images)

## Wersja 2.0.15 – 29 Jan 2017
*Wydanie przygotowane przez Becky.*
- Fixed: Improved error handling
- Fixed: Improved translations
- Fixed: Config file load/save
- Added: Option to save the number of pages as additional identifier

## Wersja 2.0.14 – 23 Jan 2017
*Wydanie przygotowane przez Becky.*
- Fixed: Better uppercase for downloaded Tags

## Wersja 2.0.13 – 19 Jan 2017
*Wydanie przygotowane przez Becky.*
- Added: Translation feature in config window
- Added: Polish translation

## Wersja 2.0.12 – 15 Jan 2017
*Wydanie przygotowane przez Becky.*
- Removed: subversions
- Fixed: Better parsing long URLs in sources
- Fixed: Better parsing approximate dates
- Fixed: Better parsing the number of pages
- Added: Option to allow download as Tags: Keywords or Genre
- Added: Option to append description/cover sources at the end of comment
- Added: Option to append the number of pages at the end of comment
- Added: Option to enable/disasble download ISBN number

## Wersja 2.0.11 – 15 Jan 2016
*Wydanie przygotowane przez Becky.*
- Two subversions: a) download Keywords as Tags; b) download Genre as Tags

## Wersja 2.0.10 – 13 Dec 2015
*Wydanie przygotowane przez Becky.*
- Changed: Properly download of books with multiple authors

## Wersja 2.0.9 – 16 Oct 2015
*Wydanie przygotowane przez Becky.*
- Changed: Download Keywords instead of Genre as Tags

## Wersja 2.0.8 – 13 Oct 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Series works at special layout for some books

## Wersja 2.0.7 – 13 Oct 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Works at special layout for some books

## Wersja 2.0.6 – 11 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Genre download

## Wersja 2.0.5 – 08 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Number of pages download (but without save to metadata)
- Fixed: Rating download

## Wersja 2.0.4 – 08 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Publisher download

## Wersja 2.0.3 – 08 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 2.0.2 – 06 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Publisher download

## Wersja 2.0.1 – 05 Jun 2015
*Wydanie przygotowane przez Becky.*
- Fixed: Authors download
- Fixed: Short descriptions download

## Wersja 2.0.0 – 14 Sep 2014
*Wydanie przygotowane przez Romana Cupisza.*
- Plugin release for Calibre 2.0

## Wersja 0.5.8 – 03 Jun 2014
*Wydanie przygotowane przez Romana Cupisza.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 0.5.7 – 24 Apr 2014
*Wydanie przygotowane przez Romana Cupisza.*
- Fixed: Plugin works again (adapting changes in lubimyczytac.pl HTML structure)

## Wersja 0.5.6 – 16 Feb 2012
*Wydanie przygotowane przez Ar't.*
- Added: Parsing series with roman numerals

## Wersja 0.5.5 – 11 Feb 2012
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Fixed: Plugin works again (adapting changes in lubimyczytac HTML structure)

## Wersja 0.5.4 – 18 Oct 2011
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Fixed: Image download - downloads bigger images again

## Wersja 0.5.3 – 18 Oct 2011
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Fixed: Rating now works with new lubimyczytac.pl 1-10 scale

## Wersja 0.5.2 – 03 Oct 2011
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Added: 'Language' tag - works with polish language only - assuming lubimyczytac.pl is for polish books. If language for book is polish it is set. Empty otherwise.
- Fixed: Title is not capitalized anymore
- Fixed: Plugin name changed (plugin was not seen in installed plugins list)

## Wersja 0.5.1 – 06 Sep 2011
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Fixed: multiple series (takes 1st one with series number given)

## Wersja 0.5.0 – 28 Aug 2011
*Wydanie przygotowane przez Jacka Bieńkowskiego*
- Initial release of plugin
