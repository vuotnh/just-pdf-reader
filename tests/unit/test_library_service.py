"""Unit tests for LibraryService application layer.

Tests cover:
- File import with format filtering
- Folder import (recursive and non-recursive)
- Duplicate detection via file hash
- Collection CRUD and membership
- Tag management
- Favorite toggling
- Reading history recording
- Error handling for non-existent books/collections
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.application.services.library_service import LibraryService, SUPPORTED_EXTENSIONS
from src.domain.enums import BookFormat, SortCriterion
from src.domain.models import Book, Collection
from src.domain.value_objects import BookFilter, ReadingPosition
from src.infrastructure.parsers.metadata_extractor import MetadataResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_repos():
    """Create mock repositories for testing."""
    book_repo = MagicMock()
    collection_repo = MagicMock()
    tag_repo = MagicMock()
    history_repo = MagicMock()
    return book_repo, collection_repo, tag_repo, history_repo


@pytest.fixture
def service(mock_repos):
    """Create a LibraryService with mocked dependencies."""
    book_repo, collection_repo, tag_repo, history_repo = mock_repos
    return LibraryService(
        book_repo=book_repo,
        collection_repo=collection_repo,
        tag_repo=tag_repo,
        history_repo=history_repo,
    )


@pytest.fixture
def sample_book():
    """Create a sample Book domain object."""
    return Book(
        id=str(uuid.uuid4()),
        title="Test Book",
        author="Test Author",
        file_path="/path/to/test.pdf",
        file_hash="abc123hash",
        format=BookFormat.PDF,
    )


@pytest.fixture
def sample_metadata():
    """Create a sample MetadataResult."""
    return MetadataResult(
        title="Extracted Title",
        author="Extracted Author",
        publisher="Publisher Inc",
        language="en",
        page_count=100,
        cover_image="base64data",
        file_hash="unique_hash_123",
    )


# ---------------------------------------------------------------------------
# Import Files Tests
# ---------------------------------------------------------------------------


class TestImportFiles:
    """Tests for import_files() method."""

    @patch("src.application.services.library_service.extract_metadata")
    def test_imports_pdf_files(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should import PDF files successfully."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        result = service.import_files([pdf_file])

        assert len(result) == 1
        assert result[0].title == "Extracted Title"
        assert result[0].format == BookFormat.PDF

    @patch("src.application.services.library_service.extract_metadata")
    def test_imports_epub_files(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should import EPUB files successfully."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        epub_file = tmp_path / "test.epub"
        epub_file.write_bytes(b"fake epub content")

        result = service.import_files([epub_file])

        assert len(result) == 1
        assert result[0].format == BookFormat.EPUB

    @patch("src.application.services.library_service.extract_metadata")
    def test_imports_azw3_files(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should import AZW3 files successfully."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        azw3_file = tmp_path / "test.azw3"
        azw3_file.write_bytes(b"fake azw3 content")

        result = service.import_files([azw3_file])

        assert len(result) == 1
        assert result[0].format == BookFormat.AZW3

    def test_filters_unsupported_formats(self, service, tmp_path):
        """Should skip files with unsupported extensions."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("some text")
        docx_file = tmp_path / "document.docx"
        docx_file.write_bytes(b"fake docx")
        jpg_file = tmp_path / "image.jpg"
        jpg_file.write_bytes(b"fake jpg")

        result = service.import_files([txt_file, docx_file, jpg_file])

        assert len(result) == 0

    @patch("src.application.services.library_service.extract_metadata")
    def test_filters_mixed_formats(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should import only supported formats from a mixed list."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        pdf_file = tmp_path / "book.pdf"
        pdf_file.write_bytes(b"fake pdf")
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("text")
        epub_file = tmp_path / "book.epub"
        epub_file.write_bytes(b"fake epub")

        result = service.import_files([pdf_file, txt_file, epub_file])

        assert len(result) == 2

    @patch("src.application.services.library_service.extract_metadata")
    def test_skips_duplicates_by_hash(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should skip files whose hash already exists in the library."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        # Simulate existing book with same hash
        book_repo.get_by_file_hash.return_value = MagicMock()

        pdf_file = tmp_path / "duplicate.pdf"
        pdf_file.write_bytes(b"duplicate content")

        result = service.import_files([pdf_file])

        assert len(result) == 0
        book_repo.add.assert_not_called()

    def test_skips_nonexistent_files(self, service):
        """Should skip paths that don't point to existing files."""
        fake_path = Path("/nonexistent/path/book.pdf")

        result = service.import_files([fake_path])

        assert len(result) == 0

    def test_empty_paths_list(self, service):
        """Should return empty list for empty input."""
        result = service.import_files([])

        assert result == []

    @patch("src.application.services.library_service.extract_metadata")
    def test_case_insensitive_extension(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should handle uppercase extensions correctly."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        pdf_file = tmp_path / "BOOK.PDF"
        pdf_file.write_bytes(b"fake pdf")

        result = service.import_files([pdf_file])

        assert len(result) == 1


# ---------------------------------------------------------------------------
# Import Folder Tests
# ---------------------------------------------------------------------------


class TestImportFolder:
    """Tests for import_folder() method."""

    @patch("src.application.services.library_service.extract_metadata")
    def test_recursive_scan(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should recursively find ebook files in subdirectories."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        # Create nested structure
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        (tmp_path / "root.pdf").write_bytes(b"pdf1")
        (sub_dir / "nested.epub").write_bytes(b"epub1")

        result = service.import_folder(tmp_path, recursive=True)

        assert len(result) == 2

    @patch("src.application.services.library_service.extract_metadata")
    def test_non_recursive_scan(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should only find files in the top-level directory when recursive=False."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        (tmp_path / "root.pdf").write_bytes(b"pdf1")
        (sub_dir / "nested.epub").write_bytes(b"epub1")

        result = service.import_folder(tmp_path, recursive=False)

        assert len(result) == 1

    def test_nonexistent_folder(self, service):
        """Should return empty list for nonexistent folder."""
        result = service.import_folder(Path("/nonexistent/folder"))

        assert result == []

    def test_empty_folder(self, service, tmp_path):
        """Should return empty list for folder with no ebook files."""
        (tmp_path / "readme.txt").write_text("hello")

        result = service.import_folder(tmp_path)

        assert result == []


# ---------------------------------------------------------------------------
# Get Books Tests
# ---------------------------------------------------------------------------


class TestGetBooks:
    """Tests for get_books() method."""

    def test_default_sort(self, service, mock_repos, sample_book):
        """Should use DATE_ADDED sort by default."""
        book_repo = mock_repos[0]
        book_repo.get_all.return_value = [sample_book]

        result = service.get_books()

        book_repo.get_all.assert_called_once_with(
            sort_by=SortCriterion.DATE_ADDED, filter=None
        )
        assert result == [sample_book]

    def test_custom_sort_and_filter(self, service, mock_repos, sample_book):
        """Should pass sort and filter to repository."""
        book_repo = mock_repos[0]
        book_repo.get_all.return_value = [sample_book]
        filter_ = BookFilter(is_favorite=True)

        result = service.get_books(sort_by=SortCriterion.TITLE, filter=filter_)

        book_repo.get_all.assert_called_once_with(
            sort_by=SortCriterion.TITLE, filter=filter_
        )


# ---------------------------------------------------------------------------
# Collection Tests
# ---------------------------------------------------------------------------


class TestCollections:
    """Tests for collection operations."""

    def test_create_collection(self, service, mock_repos):
        """Should delegate collection creation to the repository."""
        collection_repo = mock_repos[1]
        expected = Collection(id="col-1", name="Fiction")
        collection_repo.create.return_value = expected

        result = service.create_collection("Fiction")

        collection_repo.create.assert_called_once_with(name="Fiction")
        assert result == expected

    def test_add_to_collection(self, service, mock_repos):
        """Should add a book to a collection."""
        book_repo = mock_repos[0]
        book_repo.add_to_collection.return_value = True

        service.add_to_collection("book-1", "col-1")

        book_repo.add_to_collection.assert_called_once_with("book-1", "col-1")

    def test_add_to_collection_not_found(self, service, mock_repos):
        """Should raise ValueError when book or collection not found."""
        book_repo = mock_repos[0]
        book_repo.add_to_collection.return_value = False

        with pytest.raises(ValueError):
            service.add_to_collection("bad-id", "bad-col")

    def test_remove_from_collection(self, service, mock_repos):
        """Should remove a book from a collection."""
        book_repo = mock_repos[0]
        book_repo.remove_from_collection.return_value = True

        service.remove_from_collection("book-1", "col-1")

        book_repo.remove_from_collection.assert_called_once_with("book-1", "col-1")

    def test_remove_from_collection_not_found(self, service, mock_repos):
        """Should raise ValueError when removal fails."""
        book_repo = mock_repos[0]
        book_repo.remove_from_collection.return_value = False

        with pytest.raises(ValueError):
            service.remove_from_collection("bad-id", "bad-col")


# ---------------------------------------------------------------------------
# Tag Tests
# ---------------------------------------------------------------------------


class TestTags:
    """Tests for tag operations."""

    def test_add_tag(self, service, mock_repos):
        """Should add a tag to a book."""
        book_repo = mock_repos[0]
        book_repo.add_tag.return_value = True

        service.add_tag("book-1", "science-fiction")

        book_repo.add_tag.assert_called_once_with("book-1", "science-fiction")

    def test_add_tag_book_not_found(self, service, mock_repos):
        """Should raise ValueError when book not found."""
        book_repo = mock_repos[0]
        book_repo.add_tag.return_value = False

        with pytest.raises(ValueError):
            service.add_tag("bad-id", "tag")

    def test_remove_tag(self, service, mock_repos):
        """Should remove a tag from a book."""
        book_repo = mock_repos[0]
        book_repo.remove_tag.return_value = True

        service.remove_tag("book-1", "old-tag")

        book_repo.remove_tag.assert_called_once_with("book-1", "old-tag")

    def test_remove_tag_failure(self, service, mock_repos):
        """Should raise ValueError when tag removal fails."""
        book_repo = mock_repos[0]
        book_repo.remove_tag.return_value = False

        with pytest.raises(ValueError):
            service.remove_tag("bad-id", "no-tag")


# ---------------------------------------------------------------------------
# Favorite Tests
# ---------------------------------------------------------------------------


class TestFavorites:
    """Tests for set_favorite() method."""

    def test_set_favorite_true(self, service, mock_repos):
        """Should mark a book as favorite."""
        book_repo = mock_repos[0]
        book_repo.set_favorite.return_value = True

        service.set_favorite("book-1", True)

        book_repo.set_favorite.assert_called_once_with("book-1", True)

    def test_set_favorite_false(self, service, mock_repos):
        """Should unmark a book as favorite."""
        book_repo = mock_repos[0]
        book_repo.set_favorite.return_value = True

        service.set_favorite("book-1", False)

        book_repo.set_favorite.assert_called_once_with("book-1", False)

    def test_set_favorite_book_not_found(self, service, mock_repos):
        """Should raise ValueError when book not found."""
        book_repo = mock_repos[0]
        book_repo.set_favorite.return_value = False

        with pytest.raises(ValueError):
            service.set_favorite("bad-id", True)


# ---------------------------------------------------------------------------
# Reading History Tests
# ---------------------------------------------------------------------------


class TestReadingHistory:
    """Tests for record_open() method."""

    def test_record_open(self, service, mock_repos, sample_book):
        """Should record a book opening with position."""
        book_repo = mock_repos[0]
        history_repo = mock_repos[3]
        book_repo.get_by_id.return_value = sample_book
        position = ReadingPosition(page=5, scroll_offset=0.3)

        service.record_open(sample_book.id, position)

        history_repo.record_open.assert_called_once_with(sample_book.id, position)

    def test_record_open_book_not_found(self, service, mock_repos):
        """Should raise ValueError when book not found."""
        book_repo = mock_repos[0]
        book_repo.get_by_id.return_value = None
        position = ReadingPosition(page=1)

        with pytest.raises(ValueError):
            service.record_open("nonexistent", position)


# ---------------------------------------------------------------------------
# Supported Extensions Tests
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    """Tests for format validation."""

    def test_supported_extensions_set(self):
        """Should support pdf, epub, and azw3."""
        assert SUPPORTED_EXTENSIONS == {".pdf", ".epub", ".azw3"}

    @patch("src.application.services.library_service.extract_metadata")
    def test_all_supported_formats_importable(self, mock_extract, service, mock_repos, sample_metadata, tmp_path):
        """Should successfully import all three supported formats."""
        book_repo = mock_repos[0]
        mock_extract.return_value = sample_metadata
        book_repo.get_by_file_hash.return_value = None
        book_repo.add.side_effect = lambda b: b

        files = []
        for ext in [".pdf", ".epub", ".azw3"]:
            f = tmp_path / f"book{ext}"
            f.write_bytes(b"content")
            files.append(f)

        result = service.import_files(files)

        assert len(result) == 3
