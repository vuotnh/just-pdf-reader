"""Domain value objects for the AI Ebook Reader platform.

Value objects are immutable data containers that describe characteristics
or attributes but carry no unique identity.
"""

from dataclasses import dataclass, field

from src.domain.enums import (
    BookFormat,
    HighlightColor,
    MasteryLevel,
    SortCriterion,
)


@dataclass(frozen=True)
class TextPosition:
    """Represents a text selection position within a book.

    For PDF: page number + character offsets within the page.
    For EPUB/AZW3: chapter identifier + character offsets within the chapter.
    """

    page: int | None = None
    chapter: str | None = None
    start_offset: int = 0
    end_offset: int = 0


@dataclass(frozen=True)
class ReadingPosition:
    """Represents the current reading position in a book.

    For PDF: page number + scroll offset.
    For EPUB/AZW3: chapter identifier + scroll offset within chapter.
    """

    page: int | None = None
    chapter: str | None = None
    scroll_offset: float = 0.0


@dataclass(frozen=True)
class BookFilter:
    """Filter criteria for querying books in the library."""

    tag: str | None = None
    collection_id: str | None = None
    is_favorite: bool | None = None
    format: BookFormat | None = None
    sort_by: SortCriterion = SortCriterion.DATE_ADDED


@dataclass(frozen=True)
class VocabFilter:
    """Filter criteria for querying vocabulary entries."""

    book_id: str | None = None
    tag: str | None = None
    mastery_level: MasteryLevel | None = None


@dataclass(frozen=True)
class DeckFilter:
    """Filter criteria for selecting review cards in a session."""

    book_id: str | None = None
    tag: str | None = None
    mastery_level: MasteryLevel | None = None
    card_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphFilter:
    """Filter criteria for knowledge graph visualization."""

    tag: str | None = None
    book_id: str | None = None
    entity_types: list[str] = field(default_factory=list)
