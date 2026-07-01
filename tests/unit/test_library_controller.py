"""Unit tests for the Library QML controller.

Tests the BookListModel and LibraryController without requiring
a running Qt application by mocking the LibraryService.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domain.enums import BookFormat
from src.domain.models import Book, Collection
from src.presentation.controllers.library_controller import (
    BookListModel,
    BookRoles,
    LibraryController,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_book(
    id: str = "book-1",
    title: str = "Test Book",
    author: str | None = "Author",
    format: BookFormat = BookFormat.PDF,
    file_path: str = "/path/to/book.pdf",
    file_hash: str = "abc123",
    is_favorite: bool = False,
    page_count: int | None = 100,
    publisher: str | None = "Publisher",
    language: str | None = "en",
    cover_image: str | None = None,
) -> Book:
    return Book(
        id=id,
        title=title,
        author=author,
        format=format,
        file_path=file_path,
        file_hash=file_hash,
        is_favorite=is_favorite,
        page_count=page_count,
        publisher=publisher,
        language=language,
        cover_image=cover_image,
    )


@pytest.fixture
def sample_books() -> list[Book]:
    return [
        _make_book(id="b1", title="Alpha", author="Alice"),
        _make_book(id="b2", title="Beta", author="Bob", is_favorite=True),
        _make_book(id="b3", title="Gamma", author=None, page_count=None),
    ]


@pytest.fixture
def mock_service(sample_books: list[Book]) -> MagicMock:
    service = MagicMock()
    service.get_books.return_value = sample_books
    service.import_files.return_value = [sample_books[0]]
    service.import_folder.return_value = [sample_books[0], sample_books[1]]
    service.create_collection.return_value = Collection(
        id="col-1", name="Fiction"
    )
    return service


# ---------------------------------------------------------------------------
# BookListModel tests
# ---------------------------------------------------------------------------


class TestBookListModel:
    """Tests for BookListModel data access."""

    def test_row_count_empty(self, qtbot):
        model = BookListModel()
        assert model.rowCount() == 0

    def test_row_count_with_books(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        assert model.rowCount() == 3

    def test_set_books_replaces_data(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        assert model.rowCount() == 3

        model.set_books([sample_books[0]])
        assert model.rowCount() == 1

    def test_data_returns_none_for_invalid_index(self, qtbot):
        model = BookListModel()
        from PySide6.QtCore import QModelIndex
        index = model.index(999, 0)
        assert model.data(index, BookRoles.TitleRole) is None

    def test_data_title_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.TitleRole) == "Alpha"

    def test_data_author_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(1, 0)
        assert model.data(index, BookRoles.AuthorRole) == "Bob"

    def test_data_author_role_none_returns_empty(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(2, 0)
        assert model.data(index, BookRoles.AuthorRole) == ""

    def test_data_id_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.IdRole) == "b1"

    def test_data_format_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.FormatRole) == "pdf"

    def test_data_is_favorite_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        # Book b2 is favorite
        index = model.index(1, 0)
        assert model.data(index, BookRoles.IsFavoriteRole) is True

    def test_data_page_count_role_none_returns_zero(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(2, 0)
        assert model.data(index, BookRoles.PageCountRole) == 0

    def test_data_cover_image_none_returns_empty(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.CoverImageRole) == ""

    def test_data_publisher_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.PublisherRole) == "Publisher"

    def test_data_language_role(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        index = model.index(0, 0)
        assert model.data(index, BookRoles.LanguageRole) == "en"

    def test_role_names_mapping(self, qtbot):
        model = BookListModel()
        names = model.roleNames()
        assert names[BookRoles.TitleRole] == b"title"
        assert names[BookRoles.AuthorRole] == b"author"
        assert names[BookRoles.IdRole] == b"bookId"
        assert names[BookRoles.FormatRole] == b"format"
        assert names[BookRoles.FilePathRole] == b"filePath"
        assert names[BookRoles.CoverImageRole] == b"coverImage"
        assert names[BookRoles.IsFavoriteRole] == b"isFavorite"
        assert names[BookRoles.PageCountRole] == b"pageCount"
        assert names[BookRoles.PublisherRole] == b"publisher"
        assert names[BookRoles.LanguageRole] == b"language"

    def test_get_books_returns_copy(self, qtbot, sample_books):
        model = BookListModel()
        model.set_books(sample_books)
        result = model.get_books()
        assert result == sample_books
        # Modifying returned list doesn't affect model
        result.clear()
        assert model.rowCount() == 3


# ---------------------------------------------------------------------------
# LibraryController tests
# ---------------------------------------------------------------------------


class TestLibraryController:
    """Tests for LibraryController slots and signals."""

    def test_constructor_loads_books(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        mock_service.get_books.assert_called()
        assert controller._book_model.rowCount() == 3

    def test_book_model_property(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        assert controller.bookModel is controller._book_model

    def test_import_files_calls_service(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        file_paths = ["/path/to/file1.pdf", "/path/to/file2.epub"]

        with qtbot.waitSignal(controller.importComplete, timeout=1000):
            controller.importFiles(file_paths)

        mock_service.import_files.assert_called_once()
        call_args = mock_service.import_files.call_args[0][0]
        assert len(call_args) == 2
        assert all(isinstance(p, Path) for p in call_args)

    def test_import_files_emits_import_complete(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.importComplete, timeout=1000) as blocker:
            controller.importFiles(["/path/file.pdf"])

        # importComplete should emit the count of imported books
        assert blocker.args == [1]

    def test_import_files_emits_books_changed(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.booksChanged, timeout=1000):
            controller.importFiles(["/path/file.pdf"])

    def test_import_folder_calls_service(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.importComplete, timeout=1000):
            controller.importFolder("/path/to/folder", True)

        mock_service.import_folder.assert_called_once()
        call_args = mock_service.import_folder.call_args
        assert call_args[0][0] == Path("/path/to/folder")
        assert call_args[1]["recursive"] is True

    def test_import_folder_emits_import_complete_with_count(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.importComplete, timeout=1000) as blocker:
            controller.importFolder("/path/to/folder")

        assert blocker.args == [2]

    def test_create_collection_calls_service(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        result = controller.createCollection("Fiction")

        mock_service.create_collection.assert_called_once_with("Fiction")
        assert result == "col-1"

    def test_add_tag_calls_service(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.booksChanged, timeout=1000):
            controller.addTag("b1", "science")

        mock_service.add_tag.assert_called_once_with("b1", "science")

    def test_set_favorite_calls_service(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.booksChanged, timeout=1000):
            controller.setFavorite("b1", True)

        mock_service.set_favorite.assert_called_once_with("b1", True)

    def test_set_favorite_refreshes_model(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        initial_call_count = mock_service.get_books.call_count

        controller.setFavorite("b1", True)
        assert mock_service.get_books.call_count > initial_call_count

    def test_open_book_calls_record_open(self, qtbot, mock_service):
        controller = LibraryController(mock_service)

        with qtbot.waitSignal(controller.booksChanged, timeout=1000):
            controller.openBook("b1")

        mock_service.record_open.assert_called_once()
        call_args = mock_service.record_open.call_args[0]
        assert call_args[0] == "b1"
        # Position should be page=1 (start of book)
        assert call_args[1].page == 1

    def test_import_progress_signal_emitted(self, qtbot, mock_service):
        controller = LibraryController(mock_service)
        progress_values = []

        controller.importProgress.connect(lambda cur, total: progress_values.append((cur, total)))
        controller.importFiles(["/a.pdf", "/b.pdf"])

        assert len(progress_values) == 2
        assert progress_values[0] == (1, 2)
        assert progress_values[1] == (2, 2)
