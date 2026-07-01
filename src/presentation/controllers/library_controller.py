"""Library QML controller exposing library operations to QML views.

Provides a BookListModel (QAbstractListModel subclass) for grid/list view
binding and a LibraryController (QObject) with slots and signals for all
library management operations.

Requirements: 1.8, 14.1
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.library_service import LibraryService
from src.domain.models import Book


class BookRoles(IntEnum):
    """Custom roles for BookListModel data access from QML."""

    IdRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    AuthorRole = Qt.ItemDataRole.UserRole + 3
    FormatRole = Qt.ItemDataRole.UserRole + 4
    FilePathRole = Qt.ItemDataRole.UserRole + 5
    CoverImageRole = Qt.ItemDataRole.UserRole + 6
    IsFavoriteRole = Qt.ItemDataRole.UserRole + 7
    PageCountRole = Qt.ItemDataRole.UserRole + 8
    PublisherRole = Qt.ItemDataRole.UserRole + 9
    LanguageRole = Qt.ItemDataRole.UserRole + 10


class BookListModel(QAbstractListModel):
    """QAbstractListModel subclass exposing book data to QML views.

    Provides role-based data access suitable for both GridView (cover
    thumbnails) and ListView (metadata columns) bindings.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._books: list[Book] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return the number of books in the model."""
        if parent.isValid():
            return 0
        return len(self._books)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self._books):
            return None

        book = self._books[index.row()]

        if role == BookRoles.IdRole:
            return book.id
        elif role == BookRoles.TitleRole:
            return book.title
        elif role == BookRoles.AuthorRole:
            return book.author or ""
        elif role == BookRoles.FormatRole:
            return book.format.value
        elif role == BookRoles.FilePathRole:
            return book.file_path
        elif role == BookRoles.CoverImageRole:
            return book.cover_image or ""
        elif role == BookRoles.IsFavoriteRole:
            return book.is_favorite
        elif role == BookRoles.PageCountRole:
            return book.page_count or 0
        elif role == BookRoles.PublisherRole:
            return book.publisher or ""
        elif role == BookRoles.LanguageRole:
            return book.language or ""
        elif role == Qt.ItemDataRole.DisplayRole:
            return book.title

        return None

    def roleNames(self) -> dict[int, bytes]:
        """Map role enum values to QML-accessible role name strings."""
        return {
            BookRoles.IdRole: b"bookId",
            BookRoles.TitleRole: b"title",
            BookRoles.AuthorRole: b"author",
            BookRoles.FormatRole: b"format",
            BookRoles.FilePathRole: b"filePath",
            BookRoles.CoverImageRole: b"coverImage",
            BookRoles.IsFavoriteRole: b"isFavorite",
            BookRoles.PageCountRole: b"pageCount",
            BookRoles.PublisherRole: b"publisher",
            BookRoles.LanguageRole: b"language",
        }

    def set_books(self, books: list[Book]) -> None:
        """Replace the entire book list and notify views of the change."""
        self.beginResetModel()
        self._books = list(books)
        self.endResetModel()

    def get_books(self) -> list[Book]:
        """Return the current list of books."""
        return list(self._books)


class LibraryController(QObject):
    """QObject controller bridging LibraryService to QML.

    Exposes library operations as slots callable from QML and emits
    signals to notify the UI of state changes.
    """

    # Signals
    booksChanged = Signal()
    importProgress = Signal(int, int)  # (current, total)
    importComplete = Signal(int)  # number of books imported

    def __init__(
        self, library_service: LibraryService, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._service = library_service
        self._book_model = BookListModel(self)
        self._refresh_books()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(QObject, constant=True)
    def bookModel(self) -> BookListModel:  # noqa: N802
        """The book list model for QML view binding."""
        return self._book_model

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(list)
    def importFiles(self, file_paths: list[str]) -> None:  # noqa: N802
        """Import files into the library.

        Args:
            file_paths: List of file path strings selected by the user.
        """
        paths = [Path(p) for p in file_paths]
        total = len(paths)

        for i, path in enumerate(paths):
            self.importProgress.emit(i + 1, total)

        imported = self._service.import_files(paths)
        self._refresh_books()
        self.importComplete.emit(len(imported))
        self.booksChanged.emit()

    @Slot(str, bool)
    def importFolder(self, folder_path: str, recursive: bool = True) -> None:  # noqa: N802
        """Import all supported books from a folder.

        Args:
            folder_path: Path to the folder to scan.
            recursive: Whether to scan subdirectories.
        """
        folder = Path(folder_path)
        imported = self._service.import_folder(folder, recursive=recursive)
        self._refresh_books()
        self.importComplete.emit(len(imported))
        self.booksChanged.emit()

    @Slot(str, result=str)
    def createCollection(self, name: str) -> str:  # noqa: N802
        """Create a new book collection.

        Args:
            name: The name of the collection.

        Returns:
            The ID of the created collection.
        """
        collection = self._service.create_collection(name)
        return collection.id

    @Slot(str, str)
    def addTag(self, book_id: str, tag: str) -> None:  # noqa: N802
        """Add a tag to a book.

        Args:
            book_id: The ID of the book.
            tag: The tag name to add.
        """
        self._service.add_tag(book_id, tag)
        self.booksChanged.emit()

    @Slot(str, bool)
    def setFavorite(self, book_id: str, is_favorite: bool) -> None:  # noqa: N802
        """Set the favorite status of a book.

        Args:
            book_id: The ID of the book.
            is_favorite: Whether the book should be a favorite.
        """
        self._service.set_favorite(book_id, is_favorite)
        self._refresh_books()
        self.booksChanged.emit()

    @Slot(str)
    def openBook(self, book_id: str) -> None:  # noqa: N802
        """Open a book and record the access in reading history.

        Args:
            book_id: The ID of the book to open.
        """
        from src.domain.value_objects import ReadingPosition

        # Record opening with a default position (beginning of book)
        position = ReadingPosition(page=1)
        self._service.record_open(book_id, position)
        self.booksChanged.emit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_books(self) -> None:
        """Reload books from the service into the model."""
        books = self._service.get_books()
        self._book_model.set_books(books)
