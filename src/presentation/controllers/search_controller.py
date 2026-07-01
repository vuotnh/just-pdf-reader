"""Search QML controller bridging SearchService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for global search functionality including:
- Full-text search across Books, Annotations, Vocabulary, Notes
- Results grouped by category with relevance ranking
- Keyboard shortcut integration for global search activation
- Click-to-navigate on search results

Requirements: 10.1, 10.3, 10.4, 14.2, 14.6
"""

from __future__ import annotations

import json
import logging
from enum import IntEnum

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.search_service import (
    SearchCategory,
    SearchResultItem,
    SearchResults,
    SearchService,
)

logger = logging.getLogger(__name__)


class SearchResultRoles(IntEnum):
    """Custom roles for SearchResultsModel data access from QML."""

    EntityIdRole = Qt.ItemDataRole.UserRole + 1
    CategoryRole = Qt.ItemDataRole.UserRole + 2
    TitleRole = Qt.ItemDataRole.UserRole + 3
    SnippetRole = Qt.ItemDataRole.UserRole + 4
    RankRole = Qt.ItemDataRole.UserRole + 5
    BookIdRole = Qt.ItemDataRole.UserRole + 6
    PositionDataRole = Qt.ItemDataRole.UserRole + 7


class SearchResultsModel(QAbstractListModel):
    """QAbstractListModel exposing search results to QML.

    Provides role-based data access for search result items,
    sorted by relevance rank (lower rank = more relevant).
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[SearchResultItem] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return the number of search result items in the model."""
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item = self._items[index.row()]

        if role == SearchResultRoles.EntityIdRole:
            return item.entity_id
        elif role == SearchResultRoles.CategoryRole:
            return item.category.value
        elif role == SearchResultRoles.TitleRole:
            return item.title
        elif role == SearchResultRoles.SnippetRole:
            return item.snippet
        elif role == SearchResultRoles.RankRole:
            return item.rank
        elif role == SearchResultRoles.BookIdRole:
            return item.book_id or ""
        elif role == SearchResultRoles.PositionDataRole:
            return item.position_data or ""
        elif role == Qt.ItemDataRole.DisplayRole:
            return item.title

        return None

    def roleNames(self) -> dict[int, bytes]:
        """Map role enum values to QML-accessible role name strings."""
        return {
            SearchResultRoles.EntityIdRole: b"entityId",
            SearchResultRoles.CategoryRole: b"category",
            SearchResultRoles.TitleRole: b"title",
            SearchResultRoles.SnippetRole: b"snippet",
            SearchResultRoles.RankRole: b"rank",
            SearchResultRoles.BookIdRole: b"bookId",
            SearchResultRoles.PositionDataRole: b"positionData",
        }

    def set_items(self, items: list[SearchResultItem]) -> None:
        """Replace the entire results list and notify views of the change."""
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def get_items(self) -> list[SearchResultItem]:
        """Return the current list of search result items."""
        return list(self._items)


class SearchController(QObject):
    """QObject controller bridging SearchService to QML.

    Exposes search operations as slots callable from QML and emits
    signals to notify the UI of state changes. Provides a list model
    for displaying search results grouped by category.

    The controller supports:
    - Executing searches with full FTS5 query support
    - Results grouped by category (Books, Annotations, Vocabulary, Notes)
    - Navigation signals for click-to-navigate on results
    - Global search activation via keyboard shortcut (Ctrl+F)

    Requirements: 10.1, 10.3, 10.4, 14.2, 14.6
    """

    # Signals
    searchCompleted = Signal()
    resultsChanged = Signal()
    navigateToBook = Signal(str, str)  # book_id, position_data
    navigateToAnnotation = Signal(str, str)  # annotation_id, book_id
    navigateToVocabulary = Signal(str)  # entry_id
    searchActivated = Signal()  # emitted when global search shortcut is triggered
    errorOccurred = Signal(str)  # error message

    def __init__(
        self,
        search_service: SearchService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = search_service
        self._results_model = SearchResultsModel(self)
        self._current_query: str = ""
        self._total_count: int = 0
        self._is_searching: bool = False

        # Category counts
        self._books_count: int = 0
        self._annotations_count: int = 0
        self._vocabulary_count: int = 0
        self._notes_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(QObject, constant=True)
    def resultsModel(self) -> SearchResultsModel:  # noqa: N802
        """The search results list model for QML view binding."""
        return self._results_model

    @Property(str, notify=resultsChanged)
    def currentQuery(self) -> str:  # noqa: N802
        """The current search query string."""
        return self._current_query

    @Property(int, notify=resultsChanged)
    def totalCount(self) -> int:  # noqa: N802
        """Total number of search results across all categories."""
        return self._total_count

    @Property(bool, notify=resultsChanged)
    def isSearching(self) -> bool:  # noqa: N802
        """Whether a search is currently in progress."""
        return self._is_searching

    @Property(int, notify=resultsChanged)
    def booksCount(self) -> int:  # noqa: N802
        """Number of results in the Books category."""
        return self._books_count

    @Property(int, notify=resultsChanged)
    def annotationsCount(self) -> int:  # noqa: N802
        """Number of results in the Annotations category."""
        return self._annotations_count

    @Property(int, notify=resultsChanged)
    def vocabularyCount(self) -> int:  # noqa: N802
        """Number of results in the Vocabulary category."""
        return self._vocabulary_count

    @Property(int, notify=resultsChanged)
    def notesCount(self) -> int:  # noqa: N802
        """Number of results in the Notes category."""
        return self._notes_count

    # ------------------------------------------------------------------
    # Slots - Search
    # ------------------------------------------------------------------

    @Slot(str)
    def search(self, query: str) -> None:
        """Execute a full-text search across all indexed content.

        Searches Books, Annotations, Vocabulary, and Notes using FTS5.
        Results are ranked by relevance and grouped by category.

        Args:
            query: The search query string. Supports operators:
                - Exact phrase: "hello world"
                - AND (default): word1 word2
                - OR: word1 OR word2
                - Exclude: -word
        """
        if self._service is None:
            self.errorOccurred.emit("Search service not available")
            return

        self._current_query = query
        self._is_searching = True
        self.resultsChanged.emit()

        try:
            results = self._service.search(query)
            self._apply_results(results)
        except Exception as e:
            logger.exception("Search failed for query: %s", query)
            self.errorOccurred.emit(f"Search failed: {e}")
            self._clear_results()
        finally:
            self._is_searching = False
            self.resultsChanged.emit()
            self.searchCompleted.emit()

    @Slot()
    def clearSearch(self) -> None:  # noqa: N802
        """Clear the current search query and results."""
        self._current_query = ""
        self._clear_results()
        self.resultsChanged.emit()

    @Slot(str, result=str)
    def getResultsByCategory(self, category: str) -> str:  # noqa: N802
        """Get search results filtered by category as JSON.

        Args:
            category: Category name (Books, Annotations, Vocabulary, Notes).

        Returns:
            JSON array of result items for the specified category.
        """
        try:
            search_category = SearchCategory(category)
        except ValueError:
            return "[]"

        items = [
            item for item in self._results_model.get_items()
            if item.category == search_category
        ]

        return json.dumps(
            [
                {
                    "entityId": item.entity_id,
                    "category": item.category.value,
                    "title": item.title,
                    "snippet": item.snippet,
                    "rank": item.rank,
                    "bookId": item.book_id or "",
                    "positionData": item.position_data or "",
                }
                for item in items
            ],
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # Slots - Navigation
    # ------------------------------------------------------------------

    @Slot(str, str, str, str)
    def navigateToResult(self, entity_id: str, category: str, book_id: str, position_data: str) -> None:  # noqa: N802
        """Navigate to a specific search result.

        Emits the appropriate navigation signal based on the result category
        to allow the main application to open the correct view/panel.

        Args:
            entity_id: The ID of the matched entity.
            category: The category of the result (Books, Annotations, Vocabulary, Notes).
            book_id: The associated book ID (if applicable).
            position_data: Position data for navigating to the exact location.
        """
        if category == SearchCategory.BOOKS.value:
            self.navigateToBook.emit(book_id or entity_id, position_data)
        elif category == SearchCategory.ANNOTATIONS.value:
            self.navigateToAnnotation.emit(entity_id, book_id)
        elif category == SearchCategory.VOCABULARY.value:
            self.navigateToVocabulary.emit(entity_id)
        elif category == SearchCategory.NOTES.value:
            # Notes are annotations with note content — navigate same as annotations
            self.navigateToAnnotation.emit(entity_id, book_id)
        else:
            logger.warning("Unknown search result category: %s", category)

    # ------------------------------------------------------------------
    # Slots - Global Search Shortcut
    # ------------------------------------------------------------------

    @Slot()
    def activateSearch(self) -> None:  # noqa: N802
        """Activate the global search panel.

        Emits the searchActivated signal to notify QML to focus
        the search input field. Bound to keyboard shortcut (Ctrl+F).
        """
        self.searchActivated.emit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_results(self, results: SearchResults) -> None:
        """Apply search results to the model and update category counts."""
        self._results_model.set_items(results.items)
        self._total_count = results.total_count

        # Calculate category counts
        grouped = results.grouped
        self._books_count = len(grouped.get(SearchCategory.BOOKS, []))
        self._annotations_count = len(grouped.get(SearchCategory.ANNOTATIONS, []))
        self._vocabulary_count = len(grouped.get(SearchCategory.VOCABULARY, []))
        self._notes_count = len(grouped.get(SearchCategory.NOTES, []))

    def _clear_results(self) -> None:
        """Clear all results and reset category counts."""
        self._results_model.set_items([])
        self._total_count = 0
        self._books_count = 0
        self._annotations_count = 0
        self._vocabulary_count = 0
        self._notes_count = 0
