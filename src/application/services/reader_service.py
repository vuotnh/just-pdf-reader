"""Reader service implementing the IReaderService protocol.

Orchestrates book opening through a ReaderFactory pattern, dispatching to
the appropriate backend (PDF, EPUB, AZW3) based on file extension.
Coordinates: open book → restore position → connect annotations → connect dictionary.

Requirements: 1.7, 2.1, 3.1, 4.1
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.domain.enums import BookFormat
from src.domain.models import Annotation, Book
from src.domain.value_objects import ReadingPosition, TextPosition
from src.infrastructure.readers.azw3_reader_backend import (
    AZW3ReaderBackend,
    ConversionProgress,
)
from src.infrastructure.readers.epub_reader_backend import (
    AnnotationHighlight,
    EPUBReaderBackend,
    FontSettings,
    SearchResult as EPUBSearchResult,
    TocEntry as EPUBTocEntry,
)
from src.infrastructure.readers.pdf_reader_backend import (
    PDFReaderBackend,
    RenderedPage,
    SearchMatch as PDFSearchMatch,
    TocEntry as PDFTocEntry,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Reader State
# ------------------------------------------------------------------


@dataclass
class ReaderState:
    """State returned when a book is successfully opened.

    Contains the active backend, book metadata, and restored position.
    """

    book: Book
    backend: PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend
    format: BookFormat
    restored_position: ReadingPosition | None = None
    annotations: list[Annotation] = field(default_factory=list)


# ------------------------------------------------------------------
# Reader Factory
# ------------------------------------------------------------------


# Extension-to-format mapping
_EXTENSION_FORMAT_MAP: dict[str, BookFormat] = {
    ".pdf": BookFormat.PDF,
    ".epub": BookFormat.EPUB,
    ".azw3": BookFormat.AZW3,
}


class ReaderFactory:
    """Factory that creates the appropriate reader backend by file extension.

    Dispatches to:
    - PDFReaderBackend for .pdf files
    - EPUBReaderBackend for .epub files
    - AZW3ReaderBackend for .azw3 files
    """

    @staticmethod
    def get_format_for_extension(extension: str) -> BookFormat | None:
        """Determine the BookFormat for a given file extension.

        Args:
            extension: File extension including the dot (e.g. ".pdf").

        Returns:
            The corresponding BookFormat, or None if unsupported.
        """
        return _EXTENSION_FORMAT_MAP.get(extension.lower())

    @staticmethod
    def create_backend(
        file_path: str,
        format: BookFormat | None = None,
    ) -> PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend:
        """Create and open the appropriate reader backend for a file.

        Args:
            file_path: Path to the ebook file.
            format: Explicit format override. If None, determined from extension.

        Returns:
            An opened reader backend instance.

        Raises:
            ValueError: If the file format is unsupported or cannot be determined.
            RuntimeError: If the file cannot be opened by the backend.
        """
        if format is None:
            extension = Path(file_path).suffix.lower()
            format = _EXTENSION_FORMAT_MAP.get(extension)
            if format is None:
                raise ValueError(
                    f"Unsupported file format: '{extension}'. "
                    f"Supported formats: {', '.join(_EXTENSION_FORMAT_MAP.keys())}"
                )

        if format == BookFormat.PDF:
            backend = PDFReaderBackend(file_path=file_path)
        elif format == BookFormat.EPUB:
            backend = EPUBReaderBackend(file_path=file_path)
        elif format == BookFormat.AZW3:
            backend = AZW3ReaderBackend(file_path=file_path)
        else:
            raise ValueError(f"Unsupported book format: {format}")

        return backend


# ------------------------------------------------------------------
# Reader Service
# ------------------------------------------------------------------


class ReaderService:
    """Application-layer service for book reading orchestration.

    Implements the IReaderService protocol from the design document.
    Coordinates:
    - Opening books via the ReaderFactory
    - Recording opens in reading history via LibraryService
    - Restoring last reading position from history
    - Loading annotations for the book
    - Providing dictionary lookup integration for text selection

    This service acts as the central coordinator between the reader
    backends, library service, annotation service, and dictionary service.
    """

    def __init__(
        self,
        library_service: Any,
        annotation_service: Any,
        dictionary_service: Any,
        history_repo: Any,
    ) -> None:
        """Initialize the reader service.

        Args:
            library_service: The LibraryService for recording opens.
            annotation_service: The AnnotationService for loading/creating annotations.
            dictionary_service: The DictionaryService for word lookups.
            history_repo: The ReadingHistoryRepository for position persistence.
        """
        self._library_service = library_service
        self._annotation_service = annotation_service
        self._dictionary_service = dictionary_service
        self._history_repo = history_repo
        self._current_state: ReaderState | None = None
        self._progress_callback: Callable[[ConversionProgress], None] | None = None

    @property
    def current_state(self) -> ReaderState | None:
        """The currently active reader state, or None if no book is open."""
        return self._current_state

    @property
    def is_book_open(self) -> bool:
        """Whether a book is currently open."""
        return self._current_state is not None

    def set_progress_callback(
        self, callback: Callable[[ConversionProgress], None] | None
    ) -> None:
        """Set a callback for AZW3 conversion progress updates.

        Only relevant when opening AZW3 files. The callback receives
        ConversionProgress objects during the conversion phase.

        Args:
            callback: Progress callback function, or None to disable.
        """
        self._progress_callback = callback

    # ------------------------------------------------------------------
    # Book opening orchestration
    # ------------------------------------------------------------------

    def open_book(self, book_id: str) -> ReaderState:
        """Open a book for reading, orchestrating the full workflow.

        Workflow:
        1. Retrieve book metadata from the library
        2. Create the appropriate reader backend via ReaderFactory
        3. Restore last reading position from history
        4. Record the open event in reading history
        5. Load existing annotations for the book
        6. Return the complete reader state

        Args:
            book_id: The ID of the book to open.

        Returns:
            ReaderState with the active backend, book, and loaded context.

        Raises:
            ValueError: If the book is not found in the library.
            RuntimeError: If the book file cannot be opened.
        """
        # Close any currently open book
        if self._current_state is not None:
            self.close_book()

        # Step 1: Retrieve book from library
        book = self._get_book(book_id)

        # Step 2: Create reader backend via factory
        backend = self._create_backend(book)

        # Step 3: Restore last reading position
        last_position = self._restore_position(book_id, book.format, backend)

        # Step 4: Record the open event
        position_to_record = last_position or ReadingPosition(page=0, scroll_offset=0.0)
        self._record_open(book_id, position_to_record)

        # Step 5: Load annotations and connect them to the backend
        annotations = self._load_annotations(book_id, book.format, backend)

        # Build reader state
        self._current_state = ReaderState(
            book=book,
            backend=backend,
            format=book.format,
            restored_position=last_position,
            annotations=annotations,
        )

        return self._current_state

    def close_book(self) -> None:
        """Close the currently open book and release backend resources."""
        if self._current_state is None:
            return

        backend = self._current_state.backend
        if isinstance(backend, PDFReaderBackend):
            backend.close()
        elif isinstance(backend, EPUBReaderBackend):
            backend.close()
        elif isinstance(backend, AZW3ReaderBackend):
            backend.close()

        self._current_state = None

    # ------------------------------------------------------------------
    # Reading position management
    # ------------------------------------------------------------------

    def save_position(self, position: ReadingPosition) -> None:
        """Save the current reading position for the open book.

        Args:
            position: The current reading position to persist.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        self._record_open(self._current_state.book.id, position)

    def get_last_position(self, book_id: str) -> ReadingPosition | None:
        """Get the last recorded reading position for a book.

        Args:
            book_id: The ID of the book.

        Returns:
            The last ReadingPosition, or None if no history exists.
        """
        return self._history_repo.get_last_position(book_id)

    # ------------------------------------------------------------------
    # Text search delegation
    # ------------------------------------------------------------------

    def search_text(self, query: str) -> list[PDFSearchMatch | EPUBSearchResult]:
        """Search for text in the currently open book.

        Delegates to the appropriate backend's search implementation.

        Args:
            query: The text to search for.

        Returns:
            List of search matches from the active backend.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        backend = self._current_state.backend
        if isinstance(backend, PDFReaderBackend):
            return backend.search_text(query)
        elif isinstance(backend, EPUBReaderBackend):
            return backend.search_text(query)
        elif isinstance(backend, AZW3ReaderBackend):
            return backend.search_text(query)
        return []

    # ------------------------------------------------------------------
    # TOC delegation
    # ------------------------------------------------------------------

    def get_toc(self) -> list[PDFTocEntry | EPUBTocEntry]:
        """Get the table of contents for the currently open book.

        Delegates to the appropriate backend's TOC extraction.

        Returns:
            List of TOC entries from the active backend.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        backend = self._current_state.backend
        if isinstance(backend, PDFReaderBackend):
            return backend.get_toc()
        elif isinstance(backend, EPUBReaderBackend):
            return backend.toc
        elif isinstance(backend, AZW3ReaderBackend):
            return backend.toc
        return []

    # ------------------------------------------------------------------
    # Annotation integration
    # ------------------------------------------------------------------

    def create_annotation(
        self,
        position: TextPosition,
        ann_type: Any,
        color: Any = None,
        content: str | None = None,
    ) -> Annotation:
        """Create an annotation in the currently open book.

        Delegates to the AnnotationService and refreshes the backend's
        highlight rendering.

        Args:
            position: Text position for the annotation.
            ann_type: AnnotationType enum value.
            color: Optional HighlightColor enum value.
            content: Selected text or note content.

        Returns:
            The created Annotation domain object.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        annotation = self._annotation_service.create_annotation(
            book_id=self._current_state.book.id,
            position=position,
            ann_type=ann_type,
            color=color,
            content=content,
        )

        # Add to the current state's annotation list
        self._current_state.annotations.append(annotation)

        # Refresh highlights in the backend
        self._apply_highlights_to_backend(
            self._current_state.format,
            self._current_state.backend,
            self._current_state.annotations,
        )

        return annotation

    def get_annotations(self) -> list[Annotation]:
        """Get all annotations for the currently open book.

        Returns:
            List of annotations, or empty list if no book is open.
        """
        if self._current_state is None:
            return []
        return self._current_state.annotations

    def refresh_annotations(self) -> list[Annotation]:
        """Reload annotations from the database and refresh the backend.

        Useful after external annotation modifications.

        Returns:
            Updated list of annotations.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        annotations = self._annotation_service.get_annotations(
            self._current_state.book.id
        )
        self._current_state.annotations = annotations

        self._apply_highlights_to_backend(
            self._current_state.format,
            self._current_state.backend,
            annotations,
        )

        return annotations

    # ------------------------------------------------------------------
    # Dictionary integration
    # ------------------------------------------------------------------

    def lookup_word(self, word: str, language: str = "en") -> Any:
        """Look up a word in the dictionary.

        Integrates with the DictionaryService to provide inline word
        lookup for text selection in any reader backend.

        Args:
            word: The word to look up.
            language: Language code for lookup context.

        Returns:
            DictEntry if found, None otherwise.
        """
        return self._dictionary_service.lookup(word, language=language)

    def lookup_and_save_vocabulary(
        self,
        word: str,
        position: TextPosition | None = None,
        language: str = "en",
    ) -> Any:
        """Look up a word and save it to the vocabulary list.

        Combines dictionary lookup with vocabulary saving, using the
        currently open book as the source reference.

        Args:
            word: The word to look up and save.
            position: Optional text position where the word was found.
            language: Language code for lookup context.

        Returns:
            VocabularyEntry domain object if lookup succeeded, None otherwise.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        entry = self._dictionary_service.lookup(word, language=language)
        if entry is None:
            return None

        return self._dictionary_service.create_vocabulary_entry(
            word=word,
            entry=entry,
            book_id=self._current_state.book.id,
            position=position,
        )

    # ------------------------------------------------------------------
    # Page rendering (PDF-specific delegation)
    # ------------------------------------------------------------------

    def get_page(self, page_num: int, zoom: float | None = None) -> RenderedPage | None:
        """Render a page from the currently open PDF book.

        Only applicable for PDF format books.

        Args:
            page_num: The page number to render (0-indexed).
            zoom: Optional zoom level override.

        Returns:
            RenderedPage if the book is a PDF and page is valid, None otherwise.

        Raises:
            RuntimeError: If no book is currently open.
        """
        if self._current_state is None:
            raise RuntimeError("No book is currently open")

        if not isinstance(self._current_state.backend, PDFReaderBackend):
            return None

        return self._current_state.backend.render_page(page_num, zoom)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_book(self, book_id: str) -> Book:
        """Retrieve a book from the library, raising if not found."""
        from src.infrastructure.repositories.book_repository import BookRepository

        # The library service uses the book repository internally
        # We access it through the library service's book_repo
        book = self._library_service._book_repo.get_by_id(book_id)
        if book is None:
            raise ValueError(f"Book '{book_id}' not found in library.")
        return book

    def _create_backend(
        self, book: Book
    ) -> PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend:
        """Create the appropriate reader backend for a book.

        For AZW3 files, wires up the progress callback if set.
        """
        if book.format == BookFormat.AZW3 and self._progress_callback:
            backend = AZW3ReaderBackend()
            backend.set_progress_callback(self._progress_callback)
            backend.open(book.file_path)
            return backend

        return ReaderFactory.create_backend(
            file_path=book.file_path,
            format=book.format,
        )

    def _restore_position(
        self,
        book_id: str,
        format: BookFormat,
        backend: PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend,
    ) -> ReadingPosition | None:
        """Restore the last reading position in the backend.

        Args:
            book_id: The book ID to look up history for.
            format: The book's format.
            backend: The active reader backend.

        Returns:
            The restored ReadingPosition, or None if no history exists.
        """
        last_position = self._history_repo.get_last_position(book_id)
        if last_position is None:
            return None

        # Navigate the backend to the restored position
        if format == BookFormat.PDF and isinstance(backend, PDFReaderBackend):
            if last_position.page is not None:
                backend.go_to_page(last_position.page)
        elif format == BookFormat.EPUB and isinstance(backend, EPUBReaderBackend):
            if last_position.chapter is not None:
                # Find the chapter index from the chapter identifier
                chapter_idx = self._find_chapter_index(backend, last_position.chapter)
                if chapter_idx is not None:
                    backend.go_to_chapter(chapter_idx)
            elif last_position.page is not None:
                # Some EPUBs store page-based position
                backend.go_to_chapter(last_position.page)
        elif format == BookFormat.AZW3 and isinstance(backend, AZW3ReaderBackend):
            # AZW3 is a single HTML file, position is scroll-based
            pass

        return last_position

    def _record_open(self, book_id: str, position: ReadingPosition) -> None:
        """Record the open event in reading history."""
        try:
            self._library_service.record_open(book_id, position)
        except (ValueError, Exception) as e:
            # Don't fail the open operation if history recording fails
            logger.warning("Failed to record book open: %s", e)

    def _load_annotations(
        self,
        book_id: str,
        format: BookFormat,
        backend: PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend,
    ) -> list[Annotation]:
        """Load annotations for a book and apply highlights to the backend.

        Args:
            book_id: The book ID.
            format: The book's format.
            backend: The active reader backend.

        Returns:
            List of loaded annotations.
        """
        annotations = self._annotation_service.get_annotations(book_id)
        self._apply_highlights_to_backend(format, backend, annotations)
        return annotations

    def _apply_highlights_to_backend(
        self,
        format: BookFormat,
        backend: PDFReaderBackend | EPUBReaderBackend | AZW3ReaderBackend,
        annotations: list[Annotation],
    ) -> None:
        """Apply annotation highlights to the reader backend's rendering.

        For EPUB and AZW3 backends, converts annotations to AnnotationHighlight
        objects for CSS injection. For PDF, highlights are rendered as overlays
        by the presentation layer (no backend-level injection needed).
        """
        if format == BookFormat.PDF:
            # PDF annotations are rendered as coordinate overlays by the QML layer
            # No backend-level highlight injection needed
            return

        # Build AnnotationHighlight list for CSS injection
        highlights: list[AnnotationHighlight] = []
        for ann in annotations:
            if ann.color is None:
                continue

            try:
                position_data = json.loads(ann.position_data)
            except (json.JSONDecodeError, TypeError):
                continue

            highlights.append(
                AnnotationHighlight(
                    annotation_id=ann.id,
                    color=ann.color,
                    start_offset=position_data.get("start_offset", 0),
                    end_offset=position_data.get("end_offset", 0),
                )
            )

        # Apply to EPUB or AZW3 backend
        if isinstance(backend, EPUBReaderBackend):
            backend.set_highlights(highlights)
        elif isinstance(backend, AZW3ReaderBackend):
            backend.set_highlights(highlights)

    def _find_chapter_index(
        self, backend: EPUBReaderBackend, chapter_id: str
    ) -> int | None:
        """Find the spine index for a chapter identifier.

        The chapter_id stored in ReadingPosition may be a spine item href
        or an ID. This method attempts to match it against the spine.

        Args:
            backend: The EPUB reader backend.
            chapter_id: The chapter identifier from the reading position.

        Returns:
            The 0-based chapter index, or None if not found.
        """
        for idx, item in enumerate(backend.spine):
            if item.href == chapter_id or item.id == chapter_id:
                return idx

        # Try partial match (some positions store just the filename)
        for idx, item in enumerate(backend.spine):
            if chapter_id in item.href:
                return idx

        return None
