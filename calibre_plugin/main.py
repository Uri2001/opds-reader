"""main.py: A GUI to download an OPDS feed, filter out parts of the results, and download selected books from the feed into the local library"""

__author__    = "Steinar Bang"
__copyright__ = "Steinar Bang, 2015-2021"
__credits__   = ["Steinar Bang"]
__license__   = "GPL v3"

import sys
import datetime
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QStringListModel, QEvent
from PyQt6.QtWidgets import QDialog, QGridLayout, QLineEdit, QComboBox, QPushButton, QCheckBox, QMessageBox, QLabel, QAbstractItemView, QTableView, QHeaderView, QVBoxLayout, QListWidget, QListWidgetItem, QHBoxLayout

from calibre_plugins.opds_client.model import OpdsBooksModel
from calibre_plugins.opds_client.config import prefs
from calibre_plugins.opds_client import config
from calibre.ebooks.metadata.book.base import Metadata


class DynamicBook(dict):
    pass

class OpdsDialog(QDialog):

    def __init__(self, gui, icon, do_user_config):
        QDialog.__init__(self, gui)
        self.gui = gui
        self.do_user_config = do_user_config

        self.db = gui.current_db.new_api

        # The model for the book list
        self.model = OpdsBooksModel(None, self.dummy_books(), self.db)
        self.searchproxymodel = QSortFilterProxyModel(self)
        self.searchproxymodel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.searchproxymodel.setFilterKeyColumn(-1)
        self.searchproxymodel.setSourceModel(self.model)

        self.layout = QGridLayout()
        self.setLayout(self.layout)

        self.setWindowTitle('OPDS Client')
        self.setWindowIcon(icon)

        labelColumnWidths = []

        self.opdsUrlLabel = QLabel('OPDS URL: ')
        self.layout.addWidget(self.opdsUrlLabel, 0, 0)
        labelColumnWidths.append(self.layout.itemAtPosition(0, 0).sizeHint().width())

        config.convertSingleStringOpdsUrlPreferenceToListOfStringsPreference()
        self.opdsUrlEditor = QComboBox(self)
        self.opdsUrlEditor.activated.connect(self.opdsUrlEditorActivated)
        self.opdsUrlEditor.addItems(prefs['opds_url'])
        self.opdsUrlEditor.setEditable(True)
        self.opdsUrlEditor.setInsertPolicy(QComboBox.InsertAtTop)
        self.layout.addWidget(self.opdsUrlEditor, 0, 1, 1, 3)
        self.opdsUrlLabel.setBuddy(self.opdsUrlEditor)

        buttonColumnNumber = 7
        buttonColumnWidths = []
        self.about_button = QPushButton('About', self)
        self.about_button.setAutoDefault(False)
        self.about_button.clicked.connect(self.about)
        self.layout.addWidget(self.about_button, 0, buttonColumnNumber)
        buttonColumnWidths.append(self.layout.itemAtPosition(0, buttonColumnNumber).sizeHint().width()) 

        # Initially download the catalogs found in the root catalog of the URL
        # selected at startup.  Fail quietly on failing to open the URL
        catalogsTuple = self.model.downloadOpdsRootCatalog(self.gui, self.opdsUrlEditor.currentText(), False)
        print(catalogsTuple)
        firstCatalogTitle = catalogsTuple[0]
        self.currentOpdsCatalogs = catalogsTuple[1] # A dictionary of title->feedURL

        self.opdsCatalogSelectorLabel = QLabel('OPDS Catalog:')
        self.layout.addWidget(self.opdsCatalogSelectorLabel, 1, 0)
        labelColumnWidths.append(self.layout.itemAtPosition(1, 0).sizeHint().width())

        self.opdsCatalogSelector = QComboBox(self)
        self.opdsCatalogSelector.setEditable(False)
        self.opdsCatalogSelectorModel = QStringListModel(self.currentOpdsCatalogs.keys())
        self.opdsCatalogSelector.setModel(self.opdsCatalogSelectorModel)
        self.opdsCatalogSelector.setCurrentText(firstCatalogTitle)
        self.layout.addWidget(self.opdsCatalogSelector, 1, 1, 1, 3)

        self.download_opds_button = QPushButton('Download OPDS', self)
        self.download_opds_button.setAutoDefault(False)
        self.download_opds_button.clicked.connect(self.download_opds)
        self.layout.addWidget(self.download_opds_button, 1, buttonColumnNumber)
        buttonColumnWidths.append(self.layout.itemAtPosition(1, buttonColumnNumber).sizeHint().width()) 

        # Search GUI
        self.searchEditor = QLineEdit(self)
        self.searchEditor.returnPressed.connect(self.searchBookList)
        self.layout.addWidget(self.searchEditor, 2, buttonColumnNumber - 2, 1, 2)

        self.searchButton = QPushButton('Search', self)
        self.searchButton.setAutoDefault(False)
        self.searchButton.clicked.connect(self.searchBookList)
        self.layout.addWidget(self.searchButton, 2, buttonColumnNumber)
        buttonColumnWidths.append(self.layout.itemAtPosition(2, buttonColumnNumber).sizeHint().width())

        # The main book list
        self.library_view = QTableView(self)
        self.library_view.setAlternatingRowColors(True)
        self.library_view.setModel(self.searchproxymodel)
        self.library_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.library_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.library_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.library_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.resizeAllLibraryViewLinesToHeaderHeight()
        self.library_view.resizeColumnsToContents()
        self.layout.addWidget(self.library_view, 3, 0, 3, buttonColumnNumber + 1)

        self.hideNewsCheckbox = QCheckBox('Hide Newspapers', self)
        self.hideNewsCheckbox.clicked.connect(self.setHideNewspapers)
        self.hideNewsCheckbox.setChecked(prefs['hideNewspapers'])
        self.layout.addWidget(self.hideNewsCheckbox, 6, 0, 1, 3)

        self.hideBooksAlreadyInLibraryCheckbox = QCheckBox('Hide books already in library', self)
        self.hideBooksAlreadyInLibraryCheckbox.clicked.connect(self.setHideBooksAlreadyInLibrary)
        self.hideBooksAlreadyInLibraryCheckbox.setChecked(prefs['hideBooksAlreadyInLibrary'])
        self.layout.addWidget(self.hideBooksAlreadyInLibraryCheckbox, 7, 0, 1, 3)

        # Let the checkbox initial state control the filtering
        self.model.setFilterBooksThatAreNewspapers(self.hideNewsCheckbox.isChecked())
        self.model.setFilterBooksThatAreAlreadyInLibrary(self.hideBooksAlreadyInLibraryCheckbox.isChecked())

        self.downloadButton = QPushButton('Download selected books', self)
        self.downloadButton.setAutoDefault(False)
        self.downloadButton.clicked.connect(self.downloadSelectedBooks)
        self.layout.addWidget(self.downloadButton, 6, buttonColumnNumber)
        buttonColumnWidths.append(self.layout.itemAtPosition(6, buttonColumnNumber).sizeHint().width()) 

        self.fixTimestampButton = QPushButton('Fix timestamps of selection', self)
        self.fixTimestampButton.setAutoDefault(False)
        self.fixTimestampButton.clicked.connect(self.fixBookTimestamps)
        self.layout.addWidget(self.fixTimestampButton, 7, buttonColumnNumber)
        buttonColumnWidths.append(self.layout.itemAtPosition(7, buttonColumnNumber).sizeHint().width()) 

        # Make all columns of the grid layout the same width as the button column
        buttonColumnWidth = max(buttonColumnWidths)
        for columnNumber in range(0, buttonColumnNumber):
            self.layout.setColumnMinimumWidth(columnNumber, buttonColumnWidth)

        # Make sure the first column isn't wider than the labels it holds
        labelColumnWidth = max(labelColumnWidths)
        self.layout.setColumnMinimumWidth(0, labelColumnWidth)

        self.resize(self.sizeHint())

        self.catalogHistory = []               # ← navigaztion stack
        # --------------------------------------------------------------
        # 1. Loading ROOT catalog as list od subcatalogs
        catalogs = self.model.downloadOpdsRootCatalog(
            self.gui, self.opdsUrlEditor.currentText(), False
        )
        self.currentOpdsCatalogs = catalogs[1]            # dict title→url
        self.model.loadSubcatalogs(self.currentOpdsCatalogs)

        # 2. Hide outdated GUI elements
        self.opdsCatalogSelectorLabel.hide()
        self.opdsCatalogSelector.hide()
        self.download_opds_button.hide()

        # --------------------------------------------------------------
        # 3. Navigation signals «Enter / DoubleClick / Backspace»
        self.library_view.doubleClicked.connect(self._activateCurrentItem)
        self.library_view.installEventFilter(self)
        
    def opdsUrlEditorActivated(self, text):
        prefs['opds_url'] = config.saveOpdsUrlCombobox(self.opdsUrlEditor)
        catalogs = self.model.downloadOpdsRootCatalog(
            self.gui, self.opdsUrlEditor.currentText(), True
        )
        self.currentOpdsCatalogs = catalogs[1]
        self.model.loadSubcatalogs(self.currentOpdsCatalogs)

    def setHideNewspapers(self, checked):
        prefs['hideNewspapers'] = checked
        self.model.setFilterBooksThatAreNewspapers(checked)
        self.resizeAllLibraryViewLinesToHeaderHeight()

    def setHideBooksAlreadyInLibrary(self, checked):
        prefs['hideBooksAlreadyInLibrary'] = checked
        self.model.setFilterBooksThatAreAlreadyInLibrary(checked)
        self.resizeAllLibraryViewLinesToHeaderHeight()

    def searchBookList(self):
        searchString = self.searchEditor.text()
        print("starting book list search for: %s" % searchString)
        self.searchproxymodel.setFilterFixedString(searchString)

    def about(self):
        text = get_resources('about.txt')
        QMessageBox.about(self, 'About the OPDS Client plugin', text.decode('utf-8'))

    def download_opds(self):
        opdsCatalogUrl = self.currentOpdsCatalogs.get(self.opdsCatalogSelector.currentText(), None)
        if opdsCatalogUrl is None:
            # Just give up quietly
            return
        self.model.downloadOpdsCatalog(self.gui, opdsCatalogUrl)
        if self.model.isCalibreOpdsServer():
            self.model.downloadMetadataUsingCalibreRestApi(self.opdsUrlEditor.currentText())
        self.library_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.library_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.library_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.resizeAllLibraryViewLinesToHeaderHeight()
        self.resize(self.sizeHint())

    def config(self):
        self.do_user_config(parent=self)

    def downloadSelectedBooks(self):
        selectionmodel = self.library_view.selectionModel()
        if selectionmodel.hasSelection():
            rows = selectionmodel.selectedRows()
            for row in reversed(rows):
                book = row.data(Qt.UserRole)
                self.downloadBook(book)

    def downloadBook(self, book):
        if len(book.links) > 0:
            # Show Select format dialog
            dialog = SelectFormatDialog(self.gui, book.links, self)
            dialog.exec() # Use exec() for modal

    def fixBookTimestamps(self):
        selectionmodel = self.library_view.selectionModel()
        if selectionmodel.hasSelection():
            rows = selectionmodel.selectedRows()
            for row in reversed(rows):
                book = row.data(Qt.UserRole)
                self.fixBookTimestamp(book)

    def fixBookTimestamp(self, book):
        bookTimestamp = book.timestamp
        identicalBookIds = self.findIdenticalBooksForBooksWithMultipleAuthors(book)
        bookIdToValMap = {}
        for identicalBookId in identicalBookIds:
            bookIdToValMap[identicalBookId] = bookTimestamp
        if len(bookIdToValMap) < 1:
            print("Failed to set timestamp of book: %s" % book)
        self.db.set_field('timestamp', bookIdToValMap)

    def findIdenticalBooksForBooksWithMultipleAuthors(self, book):
        authorsList = book.authors
        if len(authorsList) < 2:
            return self.db.find_identical_books(book)
        # Try matching the authors one by one
        identicalBookIds = set()
        for author in authorsList:
            singleAuthorBook = Metadata(book.title, [author])
            singleAuthorIdenticalBookIds = self.db.find_identical_books(singleAuthorBook)
            identicalBookIds = identicalBookIds.union(singleAuthorIdenticalBookIds)
        return identicalBookIds

    def dummy_books(self):
        dummy_author = ' ' * 40
        dummy_title = ' ' * 60
        books_list = []
        for line in range (1, 10):
            book = DynamicBook()
            book.author = dummy_author
            book.title = dummy_title
            book.updated = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')
            book.id = ''
            books_list.append(book)
        return books_list

    def resizeAllLibraryViewLinesToHeaderHeight(self):
        rowHeight = self.library_view.horizontalHeader().height()
        for rowNumber in range (0, self.library_view.model().rowCount()):
            self.library_view.setRowHeight(rowNumber, rowHeight)


    # -----------------------------------------------------------------
    #  process keypress
    def eventFilter(self, obj, ev):
        if obj is self.library_view and ev.type() == QEvent.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._activateCurrentItem()
                return True
            if ev.key() == Qt.Key_Backspace:
                self._navigateBack()
                return True
        return super().eventFilter(obj, ev)

    # -----------------------------------------------------------------
    def _activateCurrentItem(self, index=None):
        """Enter / DoubleClick → открыть каталог или скачать книгу"""
        if index is None:
            index = self.library_view.currentIndex()
            if not index.isValid():
                return

        meta = index.data(Qt.UserRole)

        # --- SUBCATALOG? ----------------------------------------------
        if hasattr(meta, 'catalogUrl'):                # ← fixed
            # save current state for Backspace
            self.catalogHistory.append(
                (list(self.model.books), self.model.serverHeader)
            )
            self._openCatalog(meta.catalogUrl)         # ← fixed
        else:
            self.downloadBook(meta)

    # -----------------------------------------------------------------
    def _openCatalog(self, url: str):
        self.model.downloadOpdsCatalog(self.gui, url)
        if self.model.isCalibreOpdsServer():
            self.model.downloadMetadataUsingCalibreRestApi(
                self.opdsUrlEditor.currentText()
            )
        self.resizeAllLibraryViewLinesToHeaderHeight()

    # -----------------------------------------------------------------
    def _navigateBack(self):
        if not self.catalogHistory:
            return
        self.model._stop_pager()
        prev_books, prev_header = self.catalogHistory.pop()
        self.model.beginResetModel()
        self.model.books = prev_books
        self.model.serverHeader = prev_header
        self.model.filterBooks()
        self.model.endResetModel()
        self.resizeAllLibraryViewLinesToHeaderHeight()

class SelectFormatDialog(QDialog):
    # Select format before download
    def __init__(self, gui, links, parent=None):
        super().__init__(parent)
        self.gui = gui
        self.links = links
        self.selected_url = None

        self.setWindowTitle('Select format')
        self.layout = QVBoxLayout(self)

        # Format list
        self.list_widget = QListWidget(self)
        for url in self.links:
            # Extract extention as format name
            format_name = url.split('/')[-1].split('?')[0].split('.')[-1].upper()
            item = QListWidgetItem(f'{format_name} ({url.split("/")[-1]})')
            item.setData(Qt.ItemDataRole.UserRole, url) # Save URL in element data
            self.list_widget.addItem(item)
        
        self.list_widget.itemDoubleClicked.connect(self.accept) # Double click to download
        self.layout.addWidget(self.list_widget)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.download_button = QPushButton('Download selected format', self)
        self.cancel_button = QPushButton('Cancel', self)
        
        self.button_layout.addWidget(self.download_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        # Connect signals
        self.download_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

    def accept(self):
        """
        Redefine accept method for download processing.
        """
        current_item = self.list_widget.currentItem()
        if not current_item:
            return # Nothing was selected
        # Get URL from element data
        self.selected_url = current_item.data(Qt.ItemDataRole.UserRole)
        if self.selected_url:
            self.gui.download_ebook(self.selected_url)
        
        super().accept() # Close with "ОК"
