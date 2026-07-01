"""Library service implementing the ILibraryService protocol.

Orchestrates book import, collection management, tag management,
favorites, and reading history by coordinating repositories and
infrastructure components.

Requirements: 1.1–1.10
"""

from __future__ import annotations

import uuid
from pathlib import Path

from src.domain.enums import BookFormat, SortCriterion
from src.domain.models import Book, Collection, ReadingHistory
from src.domain.value_objects import BookFilter, ReadingPosition
from src.infrastructure.parsers.metadata_extractor import extract_metadata
from src.infrastructure.repositories.book_repository import (
    BookRepository,
    CollectionRepository,
    ReadingHistoryRepository,
    TagRepository,
)

# Supported file extensions for import
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".epub", ".azw3"}


class LibraryService:
    """Application-layer service for library management.

    Implements the ILibraryService protocol from the design document,
    coordinating repositories and metadata extraction to handle:
    - File/folder import with format filtering and deduplication
    - Collection CRUD and book membership
    - Tag management
    - Favorite toggling
    - Reading history recording
    """

    def __init__(
        self,
        book_repo: BookRepository,
        collection_repo: CollectionRepository,
        tag_repo: TagRepository,
        history_repo: ReadingHistoryRepository,
    ) -> None:
        self._book_repo = book_repo
        self._collection_repo = collection_repo
        self._tag_repo = tag_repo
        self._history_repo = history_repo

    # ------------------------------------------------------------------
    # Import operations
    # ------------------------------------------------------------------

    def import_files(self, paths: list[Path]) -> list[Book]:
        """Import files into the library, filtering by supported format.

        Only files with extensions .pdf, .epub, .azw3 are imported.
        Duplicate files (same SHA-256 hash) are skipped.

        Args:
            paths: List of file paths to import.

        Returns:
            List of newly imported Book domain objects.
        """
        imported: list[Book] = []

        for path in paths:
            if not self._is_supported_format(path):
                continue

            if not path.is_file():
                continue

            book = self._import_single_file(path)
            if book is not None:
                imported.append(book)

        return imported

    def import_folder(self, folder: Path, recursive: bool = True) -> list[Book]:
        """Scan a folder for supported ebook files and import them.

        Args:
            folder: The directory path to scan.
            recursive: If True, scan subdirectories recursively.

        Returns:
            List of newly imported Book domain objects.
        """
        if not folder.is_dir():
            return []

        files: list[Path] = []
        if recursive:
            for ext in SUPPORTED_EXTENSIONS:
                files.extend(folder.rglob(f"*{ext}"))
        else:
            for ext in SUPPORTED_EXTENSIONS:
                files.extend(folder.glob(f"*{ext}"))

        return self.import_files(files)

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_books(
        self, sort_by: SortCriterion = SortCriterion.DATE_ADDED, filter: BookFilter | None = None
    ) -> list[Book]:
        """Retrieve books with optional sorting and filtering.

        Args:
            sort_by: The criterion to sort results by.
            filter: Optional filter criteria.

        Returns:
            List of Book domain objects.
        """
        return self._book_repo.get_all(sort_by=sort_by, filter=filter)

    # ------------------------------------------------------------------
    # Collection operations
    # ------------------------------------------------------------------

    def create_collection(self, name: str) -> Collection:
        """Create a new book collection.

        Args:
            name: The name for the new collection.

        Returns:
            The created Collection domain object.
        """
        return self._collection_repo.create(name=name)

    def add_to_collection(self, book_id: str, collection_id: str) -> None:
        """Add a book to a collection.

        Args:
            book_id: The ID of the book to add.
            collection_id: The ID of the target collection.

        Raises:
            ValueError: If the book or collection does not exist.
        """
        success = self._book_repo.add_to_collection(book_id, collection_id)
        if not success:
            raise ValueError(
                f"Failed to add book '{book_id}' to collection '{collection_id}'. "
                "Book or collection not found."
            )

    def remove_from_collection(self, book_id: str, collection_id: str) -> None:
        """Remove a book from a collection.

        Args:
            book_id: The ID of the book to remove.
            collection_id: The ID of the collection.

        Raises:
            ValueError: If the book or collection does not exist.
        """
        success = self._book_repo.remove_from_collection(book_id, collection_id)
        if not success:
            raise ValueError(
                f"Failed to remove book '{book_id}' from collection '{collection_id}'. "
                "Book or collection not found."
            )

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def add_tag(self, book_id: str, tag: str) -> None:
        """Add a tag to a book. Creates the tag if it doesn't exist.

        Args:
            book_id: The ID of the book to tag.
            tag: The tag name to add.

        Raises:
            ValueError: If the book does not exist.
        """
        success = self._book_repo.add_tag(book_id, tag)
        if not success:
            raise ValueError(f"Book '{book_id}' not found.")

    def remove_tag(self, book_id: str, tag: str) -> None:
        """Remove a tag from a book.

        Args:
            book_id: The ID of the book.
            tag: The tag name to remove.

        Raises:
            ValueError: If the book does not exist.
        """
        success = self._book_repo.remove_tag(book_id, tag)
        if not success:
            raise ValueError(f"Failed to remove tag '{tag}' from book '{book_id}'.")

    # ------------------------------------------------------------------
    # Favorite operations
    # ------------------------------------------------------------------

    def set_favorite(self, book_id: str, is_favorite: bool) -> None:
        """Toggle the favorite status of a book.

        Args:
            book_id: The ID of the book.
            is_favorite: Whether the book should be marked as favorite.

        Raises:
            ValueError: If the book does not exist.
        """
        success = self._book_repo.set_favorite(book_id, is_favorite)
        if not success:
            raise ValueError(f"Book '{book_id}' not found.")

    # ------------------------------------------------------------------
    # Reading history
    # ------------------------------------------------------------------

    def record_open(self, book_id: str, position: ReadingPosition) -> None:
        """Record that a book was opened at a specific position.

        Args:
            book_id: The ID of the book being opened.
            position: The reading position (page/chapter + scroll offset).

        Raises:
            ValueError: If the book does not exist.
        """
        book = self._book_repo.get_by_id(book_id)
        if book is None:
            raise ValueError(f"Book '{book_id}' not found.")

        self._history_repo.record_open(book_id, position)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_supported_format(self, path: Path) -> bool:
        """Check if a file has a supported extension."""
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _import_single_file(self, path: Path) -> Book | None:
        """Import a single file, returning None if it's a duplicate.

        Extracts metadata, checks for duplicates by file hash,
        and persists the new book entry.
        """
        metadata = extract_metadata(path)

        # Skip duplicates based on file hash
        if metadata.file_hash and self._book_repo.get_by_file_hash(metadata.file_hash):
            return None

        # Determine format from extension
        format_map = {
            ".pdf": BookFormat.PDF,
            ".epub": BookFormat.EPUB,
            ".azw3": BookFormat.AZW3,
        }
        book_format = format_map[path.suffix.lower()]

        book = Book(
            id=str(uuid.uuid4()),
            title=metadata.title,
            author=metadata.author,
            publisher=metadata.publisher,
            language=metadata.language,
            page_count=metadata.page_count,
            file_path=str(path),
            file_hash=metadata.file_hash,
            format=book_format,
            cover_image=metadata.cover_image,
        )

        return self._book_repo.add(book)
