"""main.py: A GUI to download an OPDS feed, filter out parts of the results, and download selected books from the feed into the local library"""

__author__    = "Steinar Bang"
__copyright__ = "Steinar Bang, 2015-2021"
__credits__   = ["Steinar Bang"]
__license__   = "GPL v3"

import sys
import datetime
import webbrowser
import urllib.parse
try:
    from PyQt6.QtCore import Qt, QSortFilterProxyModel, QStringListModel, QEvent, QPoint, QItemSelectionModel
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QGridLayout, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QMessageBox, QLabel, QAbstractItemView, QTableView, QHeaderView,
        QVBoxLayout, QListWidget, QListWidgetItem, QHBoxLayout, QMenu,
        QStackedLayout, QWidget
    )
    from PyQt6.QtGui import QAction, QGuiApplication, QBrush, QColor
    HEADER_STRETCH = QHeaderView.ResizeMode.Stretch
except ImportError:
    from PyQt5.QtCore import Qt, QSortFilterProxyModel, QStringListModel, QEvent, QPoint, QItemSelectionModel
    from PyQt5.QtWidgets import (
        QApplication, QDialog, QGridLayout, QLineEdit, QComboBox, QPushButton,
        QCheckBox, QMessageBox, QLabel, QAbstractItemView, QTableView, QHeaderView,
        QVBoxLayout, QListWidget, QListWidgetItem, QHBoxLayout, QMenu,
        QStackedLayout, QWidget
    )
    from PyQt5.QtGui import QAction, QGuiApplication, QBrush, QColor
    HEADER_STRETCH = QHeaderView.Stretch

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
        self.model.pageLoaded.connect(self._onPageLoaded)
        self.searchproxymodel = QSortFilterProxyModel(self)
        self.searchproxymodel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.searchproxymodel.setFilterKeyColumn(-1)
        self.searchproxymodel.setDynamicSortFilter(True)
        self.searchproxymodel.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.searchproxymodel.setSourceModel(self.model)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.setWindowTitle('OPDS Client')
        self.setWindowIcon(icon)

        config.convertSingleStringOpdsUrlPreferenceToListOfStringsPreference()
        self.opdsUrlLabel = QLabel('OPDS URL: ')
        self.opdsUrlEditor = QComboBox(self)
        self.opdsUrlEditor.activated.connect(self.opdsUrlEditorActivated)
        self.opdsUrlEditor.addItems(prefs['opds_url'])
        self.opdsUrlEditor.setEditable(True)
        self.opdsUrlEditor.setInsertPolicy(QComboBox.InsertAtTop)
        self.opdsUrlLabel.setBuddy(self.opdsUrlEditor)

        self.refreshButton = QPushButton('Refresh', self)
        self.refreshButton.setAutoDefault(False)
        self.refreshButton.clicked.connect(self._refreshCurrentCatalog)

        self.about_button = QPushButton('About', self)
        self.about_button.setAutoDefault(False)
        self.about_button.clicked.connect(self.about)

        self.statusLabel = QLabel('Ready', self)
        self._isLoading = False
        self.errorLabel = QLabel('', self)
        self.errorLabel.setStyleSheet('color: #e5534b;')
        self.errorLabel.setWordWrap(True)

        self.backButton = QPushButton('Back', self)
        self.backButton.setAutoDefault(False)
        self.backButton.clicked.connect(self._navigateBack)

        self.breadcrumbLabel = QLabel('Root', self)

        # Search GUI
        self.searchEditor = QLineEdit(self)
        self.searchEditor.setPlaceholderText('Search in current catalog…')
        self.searchEditor.returnPressed.connect(self.searchBookList)

        self.searchButton = QPushButton('Search', self)
        self.searchButton.setAutoDefault(False)
        self.searchButton.clicked.connect(self.searchBookList)

        # The main book list
        self.library_view = QTableView(self)
        self.library_view.setAlternatingRowColors(True)
        self.library_view.setModel(self.searchproxymodel)
        self.library_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.library_view.horizontalHeader().setSectionResizeMode(0, HEADER_STRETCH)
        self.library_view.horizontalHeader().setSectionResizeMode(1, HEADER_STRETCH)
        self.library_view.horizontalHeader().setSectionResizeMode(2, HEADER_STRETCH)
        self.library_view.setSortingEnabled(True)
        self.library_view.sortByColumn(0, Qt.AscendingOrder)
        self.searchproxymodel.sort(0, Qt.AscendingOrder)
        self.library_view.setStyleSheet(
            "QTableView::item:hover { background-color: rgba(80, 120, 180, 80); }\n"
            "QTableView { gridline-color: rgba(255,255,255,25); }"
        )
        self.library_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.library_view.customContextMenuRequested.connect(self._showContextMenu)

        # Stack to show empty state
        self.emptyLabel = QLabel('No results', self)
        self.emptyLabel.setAlignment(Qt.AlignCenter)
        self.emptyLabel.setStyleSheet('color: #b0b0b0;')
        self.tableStackWidget = QWidget(self)
        self.tableStack = QStackedLayout(self.tableStackWidget)
        self.tableStack.setStackingMode(QStackedLayout.StackingMode.StackAll if hasattr(QStackedLayout, 'StackingMode') else QStackedLayout.StackAll)
        self.tableStack.addWidget(self.library_view)
        self.tableStack.addWidget(self.emptyLabel)

        # Filters and actions
        self.hideNewsCheckbox = QCheckBox('Hide Newspapers', self)
        self.hideNewsCheckbox.setToolTip('Hide entries marked as News in OPDS tags.')
        self.hideNewsCheckbox.clicked.connect(self.setHideNewspapers)
        self.hideNewsCheckbox.setChecked(prefs['hideNewspapers'])

        self.hideBooksAlreadyInLibraryCheckbox = QCheckBox('Hide books already in library', self)
        self.hideBooksAlreadyInLibraryCheckbox.setToolTip('Hide rows that match books already present in the local library.')
        self.hideBooksAlreadyInLibraryCheckbox.clicked.connect(self.setHideBooksAlreadyInLibrary)
        self.hideBooksAlreadyInLibraryCheckbox.setChecked(prefs['hideBooksAlreadyInLibrary'])

        self.downloadButton = QPushButton('Download selected (0)', self)
        self.downloadButton.setAutoDefault(False)
        self.downloadButton.clicked.connect(self.downloadSelectedBooks)
        self.downloadButton.setEnabled(False)

        self.fixTimestampButton = QPushButton('Fix timestamps of selection', self)
        self.fixTimestampButton.setAutoDefault(False)
        self.fixTimestampButton.clicked.connect(self.fixBookTimestamps)
        self.fixTimestampButton.setEnabled(False)

        # Layout assembly
        topRow = QHBoxLayout()
        topRow.addWidget(self.opdsUrlLabel)
        topRow.addWidget(self.opdsUrlEditor, 1)
        topRow.addWidget(self.refreshButton)
        topRow.addStretch(1)
        topRow.addWidget(self.about_button)
        self.layout.addLayout(topRow)
        self.layout.addWidget(self.errorLabel)

        # old widgets kept hidden but out of main layout
        self.opdsCatalogSelectorLabel = QLabel('OPDS Catalog:')
        self.opdsCatalogSelector = QComboBox(self)
        self.opdsCatalogSelectorModel = QStringListModel([])
        self.opdsCatalogSelector.setModel(self.opdsCatalogSelectorModel)
        self.download_opds_button = QPushButton('Download OPDS', self)
        for w in (self.opdsCatalogSelectorLabel, self.opdsCatalogSelector, self.download_opds_button):
            w.hide()

        searchRow = QHBoxLayout()
        searchRow.addWidget(self.backButton)
        searchRow.addWidget(self.breadcrumbLabel)
        searchRow.addStretch(1)
        searchRow.addWidget(self.statusLabel)
        searchRow.addSpacing(8)
        searchRow.addWidget(self.searchEditor, 1)
        searchRow.addWidget(self.searchButton)
        self.layout.addLayout(searchRow)

        self.layout.addWidget(self.tableStackWidget, 1)

        filtersRow = QHBoxLayout()
        filtersRow.addWidget(self.hideNewsCheckbox)
        filtersRow.addStretch(1)
        filtersRow.addWidget(self.downloadButton)
        self.layout.addLayout(filtersRow)

        bottomRow = QHBoxLayout()
        bottomRow.addWidget(self.hideBooksAlreadyInLibraryCheckbox)
        bottomRow.addStretch(1)
        bottomRow.addWidget(self.fixTimestampButton)
        self.layout.addLayout(bottomRow)

        self.resize(self.sizeHint())

        self.catalogHistory = []               # ← navigation stack
        self.currentCatalogUrl = None
        self.breadcrumbs = ['Root']

        self._loadRootCatalog(False)

        # 2. Hide outdated GUI elements
        self.opdsCatalogSelectorLabel.hide()
        self.opdsCatalogSelector.hide()
        self.download_opds_button.hide()

        # --------------------------------------------------------------
        # 3. Navigation signals «Enter / DoubleClick / Backspace»
        self.library_view.doubleClicked.connect(self._activateCurrentItem)
        self.library_view.installEventFilter(self)
        self.searchproxymodel.dataChanged.connect(self._updateEmptyState)
        self.searchproxymodel.modelReset.connect(self._updateEmptyState)
        self.searchproxymodel.rowsInserted.connect(self._updateEmptyState)
        self.searchproxymodel.rowsRemoved.connect(self._updateEmptyState)
        self.library_view.selectionModel().selectionChanged.connect(self._updateSelectionState)
        self._restoreColumnWidths()
        self._updateEmptyState()
        self._updateSelectionState()
        
    def opdsUrlEditorActivated(self, text):
        prefs['opds_url'] = config.saveOpdsUrlCombobox(self.opdsUrlEditor)
        self._loadRootCatalog(True)

    def setHideNewspapers(self, checked):
        prefs['hideNewspapers'] = checked
        self.model.setFilterBooksThatAreNewspapers(checked)
        self.resizeAllLibraryViewLinesToHeaderHeight()
        self._updateEmptyState()

    def setHideBooksAlreadyInLibrary(self, checked):
        prefs['hideBooksAlreadyInLibrary'] = checked
        self.model.setFilterBooksThatAreAlreadyInLibrary(checked)
        self.resizeAllLibraryViewLinesToHeaderHeight()
        self._updateEmptyState()

    def searchBookList(self):
        searchString = self.searchEditor.text()
        print("starting book list search for: %s" % searchString)
        self.searchproxymodel.setFilterFixedString(searchString)
        self._updateEmptyState()

    def about(self):
        text = get_resources('about.txt')
        QMessageBox.about(self, 'About the OPDS Client plugin', text.decode('utf-8'))

    def download_opds(self):
        self._refreshCurrentCatalog()

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
        rowHeight = self.library_view.horizontalHeader().height() + 6
        try:
            self.library_view.verticalHeader().setDefaultSectionSize(rowHeight)
        except Exception:
            pass
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
                (list(self.model.books), self.model.serverHeader, self.currentCatalogUrl, list(self.breadcrumbs))
            )
            self._updateBreadcrumb(getattr(meta, 'title', 'Catalog'), push=True)
            self._openCatalog(meta.catalogUrl)         # ← fixed
        else:
            self.downloadBook(meta)

    # -----------------------------------------------------------------
    def _openCatalog(self, url: str):
        self._setLoading(True, 'Loading first page…')
        self._setError('')
        QApplication.processEvents()
        resolved_url = self._resolveUrl(url)
        self.currentCatalogUrl = resolved_url

        def on_ready():
            self._setLoading(False, 'Loaded first page')
            self.resizeAllLibraryViewLinesToHeaderHeight()
            self._updateEmptyState()
            self._updateSelectionState()
            # If calibre server, fetch timestamps (can be slow; keep UI responsive)
            if self.model.isCalibreOpdsServer():
                try:
                    self.model.downloadMetadataUsingCalibreRestApi(
                        self.opdsUrlEditor.currentText()
                    )
                except Exception as exc:
                    self._setError(f'Failed to fetch metadata: {exc}')

        def on_error(msg):
            self._setLoading(False)
            self._setError(f'Failed to load catalog: {msg}')
            self._updateEmptyState()
            self._updateSelectionState()

        self.model.downloadOpdsCatalogAsync(self.gui, resolved_url, on_ready, on_error)

    # -----------------------------------------------------------------
    def _navigateBack(self):
        if not self.catalogHistory:
            return
        self.model._cancel_first_worker()
        self.model._stop_pager()
        prev_books, prev_header, prev_url, prev_breadcrumbs = self.catalogHistory.pop()
        self.model.beginResetModel()
        self.model.books = prev_books
        self.model.serverHeader = prev_header
        self.model.filterBooks()
        self.model.endResetModel()
        self.currentCatalogUrl = prev_url
        self.breadcrumbs = prev_breadcrumbs
        self._updateBreadcrumb()
        self.resizeAllLibraryViewLinesToHeaderHeight()
        self._updateEmptyState()
        self._updateSelectionState()

    def _loadRootCatalog(self, displayDialogOnErrors):
        self._setLoading(True, 'Loading root…')
        QApplication.processEvents()
        try:
            catalogsTuple = self.model.downloadOpdsRootCatalog(
                self.gui, self.opdsUrlEditor.currentText(), displayDialogOnErrors
            )
            self.currentOpdsCatalogs = catalogsTuple[1]
            self.currentCatalogUrl = None
            self.catalogHistory = []
            self.model.loadSubcatalogs(self.currentOpdsCatalogs)
            self.breadcrumbs = ['Root']
            self._updateBreadcrumb()
            if catalogsTuple[0] is None:
                self._setError('Failed to open the OPDS URL.')
            elif not self.currentOpdsCatalogs:
                self._setError('No catalogs found at the OPDS URL.')
            else:
                self._setError('')
        finally:
            self._setLoading(False)
            self.resizeAllLibraryViewLinesToHeaderHeight()
            self._updateEmptyState()
            self._updateSelectionState()

    def _refreshCurrentCatalog(self):
        if self.currentCatalogUrl:
            # Keep breadcrumb as-is when refreshing
            self._openCatalog(self.currentCatalogUrl)
        else:
            self._loadRootCatalog(True)

    def _setLoading(self, is_loading, message='Loading…'):
        self._isLoading = is_loading
        self.statusLabel.setText(message if is_loading else 'Ready')
        self.searchButton.setEnabled(not is_loading)
        self.refreshButton.setEnabled(not is_loading)
        try:
            if is_loading:
                QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            else:
                QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        try:
            QApplication.processEvents()
        except Exception:
            pass
        if is_loading:
            self.downloadButton.setEnabled(False)
            self.fixTimestampButton.setEnabled(False)
        else:
            self._updateSelectionState()

    def _setError(self, text):
        self.errorLabel.setText(text or '')

    def _updateBreadcrumb(self, label=None, push=False):
        if label:
            if push:
                self.breadcrumbs.append(label)
            elif self.breadcrumbs:
                self.breadcrumbs[-1] = label
            else:
                self.breadcrumbs = [label]
        breadcrumb_text = ' > '.join(self.breadcrumbs)
        self.breadcrumbLabel.setText(breadcrumb_text)

    def _updateEmptyState(self, *_args):
        rowCount = self.searchproxymodel.rowCount()
        if rowCount == 0:
            query = self.searchEditor.text().strip()
            if query:
                self.emptyLabel.setText(f"No matches for '{query}'")
            else:
                self.emptyLabel.setText('No results')
            self.tableStack.setCurrentIndex(1)
        else:
            self.tableStack.setCurrentIndex(0)

    def _updateSelectionState(self, *_args):
        selectionmodel = self.library_view.selectionModel()
        count = len(selectionmodel.selectedRows()) if selectionmodel else 0
        self.downloadButton.setText(f'Download selected ({count})')
        enabled = (count > 0) and (not self._isLoading)
        self.downloadButton.setEnabled(enabled)
        self.fixTimestampButton.setEnabled(enabled)

    def _onPageLoaded(self, batch_size: int):
        # Update status to reflect progress
        total = self.searchproxymodel.rowCount()
        if batch_size is None:
            batch_size = 0
        self.statusLabel.setText(f'Loaded {total} items (+{batch_size})')
        self._updateEmptyState()

    def _restoreColumnWidths(self):
        header = self.library_view.horizontalHeader()
        stored = prefs.get('column_widths', None)
        if isinstance(stored, list) and len(stored) >= self.model.booktableColumnCount:
            for idx in range(self.model.booktableColumnCount):
                try:
                    header.resizeSection(idx, int(stored[idx]))
                except (TypeError, ValueError):
                    pass
        try:
            header.sectionResized.connect(self._saveColumnWidths)
        except Exception:
            pass

    def _saveColumnWidths(self, *_args):
        header = self.library_view.horizontalHeader()
        widths = [header.sectionSize(i) for i in range(self.model.booktableColumnCount)]
        prefs['column_widths'] = widths

    def _resolveUrl(self, url: str) -> str:
        base = self.currentCatalogUrl or self.opdsUrlEditor.currentText()
        try:
            return urllib.parse.urljoin(base, url)
        except Exception:
            return url

    def _currentSelectionBooks(self):
        selectionmodel = self.library_view.selectionModel()
        if not selectionmodel or not selectionmodel.hasSelection():
            return []
        rows = selectionmodel.selectedRows()
        books = []
        for row in rows:
            meta = row.data(Qt.UserRole)
            if meta:
                books.append(meta)
        return books

    def _showContextMenu(self, point: QPoint):
        global_pos = self.library_view.viewport().mapToGlobal(point)
        index = self.library_view.indexAt(point)
        if index.isValid():
            selection_model = self.library_view.selectionModel()
            if selection_model is not None and not selection_model.isSelected(index):
                selection_model.select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        selection = self._currentSelectionBooks()
        if not selection:
            return
        menu = QMenu(self)

        copyLinkAction = QAction('Copy link', self)
        copyLinkAction.triggered.connect(lambda: self._copyLink(selection))
        menu.addAction(copyLinkAction)

        openInBrowserAction = QAction('Open in browser', self)
        openInBrowserAction.triggered.connect(lambda: self._openInBrowser(selection))
        menu.addAction(openInBrowserAction)

        showMetadataAction = QAction('Show metadata', self)
        showMetadataAction.triggered.connect(lambda: self._showMetadataDialog(selection))
        menu.addAction(showMetadataAction)

        menu.exec(global_pos)

    def _copyLink(self, books):
        link = None
        first = books[0]
        if getattr(first, 'links', []):
            link = first.links[0]
        elif hasattr(first, 'catalogUrl'):
            link = first.catalogUrl
        if link:
            QGuiApplication.clipboard().setText(link)

    def _openInBrowser(self, books):
        link = None
        first = books[0]
        if getattr(first, 'links', []):
            link = first.links[0]
        elif hasattr(first, 'catalogUrl'):
            link = first.catalogUrl
        if link:
            webbrowser.open(link)

    def _showMetadataDialog(self, books):
        first = books[0]
        title = getattr(first, 'title', 'Metadata')
        authors = ', '.join(getattr(first, 'author', []))
        timestamp = getattr(first, 'timestamp', None)
        ts_text = timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else '—'
        info = f"Title: {title}\\nAuthor(s): {authors}\\nUpdated: {ts_text}"
        QMessageBox.information(self, 'Metadata', info)

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
