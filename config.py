#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
"""
Konfiguracja wtyczki LubimyCzytać: klucze ustawień, wartości domyślne
i okno konfiguracji (``ConfigWidget``) wyświetlane w calibre po kliknięciu
„Konfiguruj” przy źródle metadanych.

Ustawienia są przechowywane w pliku JSON (``plugin_prefs``) pod jednym
kluczem ``STORE_NAME``. Pozostałe moduły odczytują je wzorem::

    cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.KLUCZ, cfg.DEFAULT_STORE_VALUES[cfg.KLUCZ])

Dodając nową opcję, trzeba uzupełnić cztery miejsca: stałą z nazwą klucza,
wpis w ``DEFAULT_STORE_VALUES``, kontrolkę w ``ConfigWidget.__init__``
oraz zapis w ``ConfigWidget.commit``. Warto też dopisać ją do listy
``config_labels`` w ``identify`` (``__init__.py``), żeby trafiała do logu.

Napisy widoczne w oknie są tłumaczone (``_()``); ich źródła znajdują się
w katalogu ``translations`` – zmiana napisu w kodzie wymaga aktualizacji
plików ``.po``/``.mo``.
"""
from __future__ import (unicode_literals, division, absolute_import, print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, Roman Cupisz <roman.cupisz+calibre@gmail.com>, 2015-2026 enhancements by Becky <becky@fr.pl>'
__docformat__ = 'restructuredtext en'

from six import text_type as unicode

# Biblioteki PyQt: calibre >= 6 udostępnia moduł qt.core, starsze – PyQt5
try:
    from qt.core import (QLabel, QGridLayout, Qt, QGroupBox, QCheckBox, QComboBox, QtWidgets)
except:
    from PyQt5 import QtWidgets
    from PyQt5.Qt import QLabel, QGridLayout, Qt, QGroupBox, QCheckBox, QComboBox

from calibre.gui2.metadata.config import ConfigWidget as DefaultConfigWidget
from calibre.utils.config import JSONConfig

try:
    load_translations()
except NameError:
    pass  # load_translations() istnieje od calibre 1.9

# Klucz, pod którym w pliku JSON zapisany jest słownik wszystkich ustawień
STORE_NAME = 'Options'

# --- Wyszukiwanie i dopasowywanie ---
KEY_MAX_DOWNLOADS = 'maxDownloads'          # maks. liczba kandydatów z listy wyników
FAST_MATCH = 'fastMatch'                    # pierwszy wynik zgodny z tytułem i autorem kończy szukanie
LC_ISSUE = 'LCissue'                        # wyszukiwarka LC ma problemy – szukaj tylko po tytule
PREFER_ISBN_MATCH = 'preferISBNMatch'       # wybierz wydanie o ISBN zgodnym z calibre
SUGGEST_MANUAL_SEARCH = 'suggestManualSearch'  # przy braku wyników wirtualny wynik z linkami do ręcznego szukania (tylko okno pobierania)

# --- Metadane ---
TAGS_AS = 'appendasTags'                    # co trafia do etykiet: 0 = kategoria, 1 = słowa kluczowe
REPLACE_ISBN = 'replaceISBN'                # pobieraj ISBN z LC (zastępując istniejący)
SWAP_NAMES = 'swapNames'                    # zapis autorów „Nazwisko Imię”

# --- Dołączane na początku komentarza (informacje o innych wydaniach) ---
BEFORE_OTHER_EDITIONS_EXIST = 'beforeOtherEditionsExist'
BEFORE_OTHER_EDITIONS_ALL = 'beforeOtherEditionsAll'
BEFORE_OTHER_EDITIONS_SHORT = 'beforeOtherEditionsShort'
BEFORE_HR = 'beforeHorizontalLine'          # linia pozioma między listą wydań a opisem

# --- Dołączane na końcu komentarza ---
APPEND_PAGES = 'appendPages'
APPEND_PAGES_NEW = 'appendPagesSimplified'  # uproszczony zapis liczby stron („Liczba stron w książce: N”)
APPEND_ORIGINAL_TITLE = 'appendOriginalTitle'
APPEND_TRANSLATION = 'appendTranslation'
APPEND_SERWYD = 'appendSerWyd'              # seria wydawnicza (nie cykl!)
APPEND_GENRE = 'appendGenre'
APPEND_KEYWORDS = 'appendKeywords'
APPEND_RATING = 'appendRating'
APPEND_ID = 'appendID'
APPEND_RATING_COUNT = 'appendRatingCount'
APPEND_FIRST_PUBDATE = 'appendDateFirstEdition'
APPEND_FIRST_PUBDATE_PL = 'appendDateFirstPolishEdition'

DEFAULT_STORE_VALUES = {
    KEY_MAX_DOWNLOADS: 4,
    TAGS_AS: 0,
    REPLACE_ISBN: False,
    FAST_MATCH: True,
    BEFORE_OTHER_EDITIONS_EXIST: False,
    BEFORE_OTHER_EDITIONS_ALL: False,
    BEFORE_OTHER_EDITIONS_SHORT: False,
    BEFORE_HR: False,
    APPEND_PAGES: True,
    APPEND_PAGES_NEW: False,
    APPEND_ORIGINAL_TITLE: False,
    APPEND_TRANSLATION: False,
    APPEND_SERWYD: False,
    APPEND_GENRE: False,
    APPEND_KEYWORDS: False,
    APPEND_RATING: False,
    APPEND_ID: False,
    APPEND_RATING_COUNT: False,
    APPEND_FIRST_PUBDATE: False,
    APPEND_FIRST_PUBDATE_PL: False,
    SWAP_NAMES: False,
    LC_ISSUE: False,
    PREFER_ISBN_MATCH: False,
    SUGGEST_MANUAL_SEARCH: False
}

# Plik z ustawieniami. Zgodnie z konwencją calibre powinien leżeć
# w metadata_sources/, ale dla zachowania wstecznej zgodności
# (ustawienia użytkowników z wielu lat) pozostaje w katalogu wtyczek.
plugin_prefs = JSONConfig('plugins/LubimyCzytac.pl')

# Wartości domyślne – używane, gdy w pliku brakuje klucza
plugin_prefs.defaults[STORE_NAME] = DEFAULT_STORE_VALUES

class ConfigWidget(DefaultConfigWidget):
    """
    Okno konfiguracji wtyczki. Rozszerza domyślne okno calibre (wybór
    pobieranych pól) o własne grupy opcji:

    * „Other options” – limit wyników, etykiety, ISBN, szybkie dopasowanie,
      preferowanie ISBN, tryb problemów z wyszukiwarką LC;
    * „Append at the beginning of the comment” – informacje o innych wydaniach;
    * „The date of the first publication” – daty pierwszych wydań;
    * „Reverse order in the author(s) field” – zapis „Nazwisko Imię”;
    * „Append at the end of the comment” – dodatkowe informacje w opisie.

    Kontrolki są rozmieszczane w siatce ``self.l`` odziedziczonej z calibre.
    """

    def __init__(self, plugin):
        """Buduje kontrolki i ustawia je zgodnie z zapisaną konfiguracją."""
        DefaultConfigWidget.__init__(self, plugin)

        c = plugin_prefs[STORE_NAME]

        # --- Grupa: Other options ---
        other_group_box = QGroupBox(_('Other options'), self)
        self.l.addWidget(other_group_box, self.l.rowCount(), 0, 1, 2)
        other_group_box_layout = QGridLayout()
        other_group_box.setLayout(other_group_box_layout)

        max_label = QLabel(_('Maximum title/author search matches to evaluate (1 = fastest):'), self)
        max_label.setToolTip(_('Increasing this value will take effect when doing\n'
                             'title/author searches to consider more matches.\n\n'
                             'This will increase the potential likelihood of not missing result\n'
                             'although it does not guaranteed.'))
        self.lc_search_engine_issue_check = QCheckBox(_('LC website has search engine issues'), self)
        self.lc_search_engine_issue_check.setToolTip(_('You can check this box when there are issues with the internal search engine on the LC site\n(of course, the problem may be of a different nature).'))

        tags_label = QLabel(_('Append to Tags field in the Metadata:'), self)
        tags_label.setToolTip(_('The genre or the keywords taken from LC will be appended as tags.'))
        self.replaceISBN_check = QCheckBox(_('Download the ISBN number from the LC'), self)
        self.replaceISBN_check.setToolTip(_('Replace the ISBN number when downloaded from the LC.\n'
                                            'If unchecked – leave the existing number unchanged.'))
        self.fastmatch_check = QCheckBox(_('Fast matching (the first one found that matches the title and author)'), self)
        self.fastmatch_check.setToolTip(_('This is a not perfect solution.'))
        self.prefer_isbn_match_check = QCheckBox(_('Prefer matching ISBN'), self)
        self.prefer_isbn_match_check.setToolTip(_('When an ISBN is supplied, check other editions and prefer an exact ISBN match.\nThis may require additional requests to LubimyCzytac.pl.'))

        other_group_box_layout.addWidget(max_label, 0, 0, 1, 1)
        other_group_box_layout.addWidget(tags_label, 1, 0, 1, 1)
        other_group_box_layout.addWidget(self.replaceISBN_check, 2, 0, 1, 1)
        other_group_box_layout.addWidget(self.fastmatch_check, 3, 0, 1, 1)
        other_group_box_layout.addWidget(self.prefer_isbn_match_check, 4, 0, 1, 1)
        other_group_box_layout.addWidget(self.lc_search_engine_issue_check, 5, 0, 1, 1)

        # Podpowiedź ręcznego wyszukania: wirtualny wynik z linkami, gdy LC nic nie zna.
        # Tylko w oknie pojedynczego pobierania – w masowym calibre zastosowałoby go bez pytania.
        self.suggest_manual_search_check = QCheckBox(_('Suggest a manual search when nothing is found'), self)
        self.suggest_manual_search_check.setToolTip(_('When LubimyCzytac does not know the title, add a virtual result whose description\n'
            'contains links to a web search limited to lubimyczytac.pl and instructions for the lubimyczytac:<ID> identifier.\n'
            'Shown only in the single-book download window, never in bulk download.\n'
            'If you use bulk download with LubimyCzytac, keep this option disabled.'))
        other_group_box_layout.addWidget(self.suggest_manual_search_check, 6, 0, 1, 1)

        self.replaceISBN_check.setChecked(c.get(REPLACE_ISBN, DEFAULT_STORE_VALUES[REPLACE_ISBN]))
        self.lc_search_engine_issue_check.setChecked(c.get(LC_ISSUE, DEFAULT_STORE_VALUES[LC_ISSUE]))
        self.fastmatch_check.setChecked(c.get(FAST_MATCH, DEFAULT_STORE_VALUES[FAST_MATCH]))
        self.prefer_isbn_match_check.setChecked(c.get(PREFER_ISBN_MATCH, DEFAULT_STORE_VALUES[PREFER_ISBN_MATCH]))
        self.suggest_manual_search_check.setChecked(c.get(SUGGEST_MANUAL_SEARCH, DEFAULT_STORE_VALUES[SUGGEST_MANUAL_SEARCH]))

        self.max_downloads_spin = QtWidgets.QSpinBox(self)
        self.max_downloads_spin.setMinimum(1)
        self.max_downloads_spin.setMaximum(17)
        self.max_downloads_spin.setProperty('value', c.get(KEY_MAX_DOWNLOADS, DEFAULT_STORE_VALUES[KEY_MAX_DOWNLOADS]))

        other_group_box_layout.addWidget(self.max_downloads_spin, 0, 1, 1, 1)

        # Lista rozwijana: indeks 0 = kategoria (genre), 1 = słowa kluczowe
        self.asTags = QComboBox()
        other_group_box_layout.addWidget(self.asTags, 1, 1, 1, 1)
        self.asTags.addItems([_('Genre (Kategoria)'), _('Keywords')])
        if c.get(TAGS_AS, DEFAULT_STORE_VALUES[TAGS_AS]) == 0:
            self.asTags.setCurrentIndex(0)
        else:
            self.asTags.setCurrentIndex(1)
        other_group_box_layout.setColumnStretch(2, 1)

        # --- Grupa: Dołączanie na początku komentarza ---
        before_group_box = QGroupBox(_('Append at the beginning of the comment'), self)
        self.l.addWidget(before_group_box, self.l.rowCount(), 0, 1, 1)
        before_group_box_layout = QGridLayout()
        before_group_box_layout.setAlignment(Qt.AlignTop)
        before_group_box.setLayout(before_group_box_layout)

        self.bother_editions_exist_check = QCheckBox(_('Inform me of existing editions'), self)
        self.bother_editions_exist_check.setToolTip(_('If other editions exist - inform about it.'))
        self.bother_editions_all_check = QCheckBox(_('Full list of the other editions'), self)
        self.bother_editions_all_check.setToolTip(_('If other editions exist - list them all.'))
        self.bother_editions_short_check = QCheckBox(_('Short list of the other editions'), self)
        self.bother_editions_short_check.setToolTip(_('List of the other editions (without links).'))
        self.bhr_check = QCheckBox(_('Add horizontal line before the comment'), self)
        self.bhr_check.setToolTip(_('If other editions exist - add horizontal line before the comment.'))

        before_group_box_layout.addWidget(self.bother_editions_exist_check, 0, 0, 1, 1)
        before_group_box_layout.addWidget(self.bother_editions_all_check, 1, 0, 1, 1)
        before_group_box_layout.addWidget(self.bother_editions_short_check, 2, 0, 1, 1)
        before_group_box_layout.addWidget(self.bhr_check, 3, 0, 1, 1)

        self.bother_editions_exist_check.setChecked(c.get(BEFORE_OTHER_EDITIONS_EXIST, DEFAULT_STORE_VALUES[BEFORE_OTHER_EDITIONS_EXIST]))
        self.bother_editions_all_check.setChecked(c.get(BEFORE_OTHER_EDITIONS_ALL, DEFAULT_STORE_VALUES[BEFORE_OTHER_EDITIONS_ALL]))
        self.bother_editions_short_check.setChecked(c.get(BEFORE_OTHER_EDITIONS_SHORT, DEFAULT_STORE_VALUES[BEFORE_OTHER_EDITIONS_SHORT]))
        self.bhr_check.setChecked(c.get(BEFORE_HR, DEFAULT_STORE_VALUES[BEFORE_HR]))

        # --- Grupa: Data pierwszego wydania ---
        pubdate_group_box = QGroupBox(_('The date of the first publication'), self)
        self.l.addWidget(pubdate_group_box, self.l.rowCount(), 0, 1, 1)
        pubdate_group_box_layout = QGridLayout()
        pubdate_group_box_layout.setAlignment(Qt.AlignTop)
        pubdate_group_box.setLayout(pubdate_group_box_layout)

        self.afirst_pubdate_check = QCheckBox(_('The date of the first publication'), self)
        self.afirst_pubdate_check.setToolTip(_('If the information about the book will contain\n'
                                       'the date of the first publication\n'
                                       '- it will be appended at the end of the comment.'))
        self.afirst_pl_pubdate_check = QCheckBox(_('The date of the first publication in Poland'), self)
        self.afirst_pl_pubdate_check.setToolTip(_('If the information about the book will contain\n'
                                       'the date of the first publication in Poland\n'
                                       '- it will be appended at the end of the comment.'))

        pubdate_group_box_layout.addWidget(self.afirst_pubdate_check, 0, 0, 1, 1)
        pubdate_group_box_layout.addWidget(self.afirst_pl_pubdate_check, 1, 0, 1, 1)

        self.afirst_pubdate_check.setChecked(c.get(APPEND_FIRST_PUBDATE, DEFAULT_STORE_VALUES[APPEND_FIRST_PUBDATE]))
        self.afirst_pl_pubdate_check.setChecked(c.get(APPEND_FIRST_PUBDATE_PL, DEFAULT_STORE_VALUES[APPEND_FIRST_PUBDATE_PL]))

        # --- Grupa: Najpierw nazwisko ---
        swap_names_group_box = QGroupBox(_('Reverse order in the author(s) field'), self)
        self.l.addWidget(swap_names_group_box, self.l.rowCount(), 0, 1, 1)
        swap_names_group_box_layout = QGridLayout()
        swap_names_group_box_layout.setAlignment(Qt.AlignTop)
        swap_names_group_box.setLayout(swap_names_group_box_layout)

        self.swap_names_check = QCheckBox(_('Last Name First Name in authors'), self)
        self.swap_names_check.setToolTip(_('For users who prefer a surname before the first name in author metadata.'))

        swap_names_group_box_layout.addWidget(self.swap_names_check, 0, 0, 1, 1)

        self.swap_names_check.setChecked(c.get(SWAP_NAMES, DEFAULT_STORE_VALUES[SWAP_NAMES]))

        # --- Grupa: Dołączanie na końcu komentarza ---
        # Trzy powyższe grupy zajęły kolumnę 0 w trzech ostatnich wierszach siatki;
        # ta grupa wypełnia obok nich kolumnę 1, rozciągnięta na te same trzy wiersze.
        append_group_box = QGroupBox(_('Append at the end of the comment'), self)
        self.l.addWidget(append_group_box, self.l.rowCount()-3, 1, 3, 1)
        append_group_box_layout = QGridLayout()
        append_group_box.setLayout(append_group_box_layout)

        self.apages_check = QCheckBox(_('Number of pages'), self)
        self.apages_check.setToolTip(_('If the information about the book will contain the number of pages\n'
                                       '- it will be appended at the end of the comment.\n'
                                       'Form: Książka ma 123 strony.'))
        self.apages_new_check = QCheckBox(_('Simplified form'), self)
        self.apages_new_check.setToolTip(_('Use form: Liczba stron w książce: 123'))
        self.aoriginaltitle_check = QCheckBox(_('Original title'), self)
        self.aoriginaltitle_check.setToolTip(_('If the information about the book will contain the original title\n'
                                       '- it will be appended at the end of the comment.'))
        self.atranslation_check = QCheckBox(_('Translator(s)'), self)
        self.atranslation_check.setToolTip(_('If the information about the book will contain info about translators\n'
                                       '- it will be appended at the end of the comment.'))
        self.aserwyd_check = QCheckBox(_('Book series (marketed as a group)'), self)
        self.aserwyd_check.setToolTip(_('If the information about the book will contain info about the book series\n'
                                       '- it will be appended at the end of the comment.'))
        self.agenre_check = QCheckBox(_('Genre (Kategoria)'), self)
        self.agenre_check.setToolTip(_('Genre be appended at the end of the comment.'))
        self.akeywords_check = QCheckBox(_('Keywords'), self)
        self.akeywords_check.setToolTip(_('If the information about the book will contain the keywords\n'
                                       '- it will be appended at the end of the comment.'))
        self.arating_check = QCheckBox(_('Rating'), self)
        self.arating_check.setToolTip(_('Append rating at the end of the comment.'))
        self.aratingcount_check = QCheckBox(_('Rating Count'), self)
        self.aratingcount_check.setToolTip(_('Append rating count at the end of the comment.'))
        self.aid_check = QCheckBox(_('ID'), self)
        self.aid_check.setToolTip(_('Append ID at the end of the comment.'))

        # Wiersz 0 pozostaje pusty (kiedyś była tu opcja „źródła opisu”, usunięta w 2.0.19)
        append_group_box_layout.addWidget(self.apages_check, 1, 0, 1, 1)
        append_group_box_layout.addWidget(self.aoriginaltitle_check, 2, 0, 1, 1)
        append_group_box_layout.addWidget(self.atranslation_check, 3, 0, 1, 1)
        append_group_box_layout.addWidget(self.aserwyd_check, 4, 0, 1, 1)
        append_group_box_layout.addWidget(self.agenre_check, 5, 0, 1, 1)
        append_group_box_layout.addWidget(self.akeywords_check, 6, 0, 1, 1)
        append_group_box_layout.addWidget(self.arating_check, 7, 0, 1, 1)
        append_group_box_layout.addWidget(self.aratingcount_check, 8, 0, 1, 1)
        append_group_box_layout.addWidget(self.aid_check, 9, 0, 1, 1)
        append_group_box_layout.addWidget(self.apages_new_check, 1, 1, 1, 1)

        self.apages_check.setChecked(c.get(APPEND_PAGES, DEFAULT_STORE_VALUES[APPEND_PAGES]))
        self.apages_new_check.setChecked(c.get(APPEND_PAGES_NEW, DEFAULT_STORE_VALUES[APPEND_PAGES_NEW]))
        self.aoriginaltitle_check.setChecked(c.get(APPEND_ORIGINAL_TITLE, DEFAULT_STORE_VALUES[APPEND_ORIGINAL_TITLE]))
        self.atranslation_check.setChecked(c.get(APPEND_TRANSLATION, DEFAULT_STORE_VALUES[APPEND_TRANSLATION]))
        self.aserwyd_check.setChecked(c.get(APPEND_SERWYD, DEFAULT_STORE_VALUES[APPEND_SERWYD]))
        self.agenre_check.setChecked(c.get(APPEND_GENRE, DEFAULT_STORE_VALUES[APPEND_GENRE]))
        self.akeywords_check.setChecked(c.get(APPEND_KEYWORDS, DEFAULT_STORE_VALUES[APPEND_KEYWORDS]))
        self.arating_check.setChecked(c.get(APPEND_RATING, DEFAULT_STORE_VALUES[APPEND_RATING]))
        self.aratingcount_check.setChecked(c.get(APPEND_RATING_COUNT,DEFAULT_STORE_VALUES[APPEND_RATING_COUNT]))
        self.aid_check.setChecked(c.get(APPEND_ID, DEFAULT_STORE_VALUES[APPEND_ID]))

    def commit(self):
        """
        Zapisuje stan kontrolek do pliku ustawień (wywoływane przez calibre
        po kliknięciu „OK”). Najpierw zapisuje się część odziedziczona z calibre
        (wybór pól), potem nasz słownik – zastępowany w całości.
        """
        DefaultConfigWidget.commit(self)
        new_prefs = {}
        new_prefs[KEY_MAX_DOWNLOADS] = int(unicode(self.max_downloads_spin.value()))
        new_prefs[TAGS_AS] = int(unicode(self.asTags.currentIndex()))
        new_prefs[REPLACE_ISBN] = self.replaceISBN_check.isChecked()
        new_prefs[LC_ISSUE] = self.lc_search_engine_issue_check.isChecked()
        new_prefs[FAST_MATCH] = self.fastmatch_check.isChecked()
        new_prefs[PREFER_ISBN_MATCH] = self.prefer_isbn_match_check.isChecked()
        new_prefs[SUGGEST_MANUAL_SEARCH] = self.suggest_manual_search_check.isChecked()

        new_prefs[BEFORE_OTHER_EDITIONS_EXIST] = self.bother_editions_exist_check.isChecked()
        new_prefs[BEFORE_OTHER_EDITIONS_ALL] = self.bother_editions_all_check.isChecked()
        new_prefs[BEFORE_OTHER_EDITIONS_SHORT] = self.bother_editions_short_check.isChecked()
        new_prefs[BEFORE_HR] = self.bhr_check.isChecked()
        new_prefs[APPEND_PAGES] = self.apages_check.isChecked()
        new_prefs[APPEND_PAGES_NEW] = self.apages_new_check.isChecked()
        new_prefs[APPEND_ORIGINAL_TITLE] = self.aoriginaltitle_check.isChecked()
        new_prefs[APPEND_TRANSLATION] = self.atranslation_check.isChecked()
        new_prefs[APPEND_SERWYD] = self.aserwyd_check.isChecked()
        new_prefs[APPEND_GENRE] = self.agenre_check.isChecked()
        new_prefs[APPEND_KEYWORDS] = self.akeywords_check.isChecked()
        new_prefs[APPEND_RATING] = self.arating_check.isChecked()
        new_prefs[APPEND_RATING_COUNT] = self.aratingcount_check.isChecked()
        new_prefs[APPEND_ID] = self.aid_check.isChecked()
        new_prefs[APPEND_FIRST_PUBDATE] = self.afirst_pubdate_check.isChecked()
        new_prefs[APPEND_FIRST_PUBDATE_PL] = self.afirst_pl_pubdate_check.isChecked()
        new_prefs[SWAP_NAMES] = self.swap_names_check.isChecked()
        plugin_prefs[STORE_NAME] = new_prefs
