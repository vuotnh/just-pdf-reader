"""Domain models for the AI Ebook Reader platform.

Pure Python dataclasses with no framework dependencies.
These represent the core business entities of the application.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.enums import (
    AnnotationType,
    BookFormat,
    CardType,
    HighlightColor,
    MasteryLevel,
    Rating,
    SRAlgorithm,
)


@dataclass
class Book:
    """A document (PDF, EPUB, or AZW3) in the user's library."""

    id: str
    title: str
    file_path: str
    file_hash: str
    format: BookFormat
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    page_count: int | None = None
    cover_image: str | None = None  # Base64-encoded thumbnail
    is_favorite: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Annotation:
    """A user annotation (highlight, underline, note, or comment) on book content."""

    id: str
    book_id: str
    type: AnnotationType
    selected_text: str
    position_data: str  # JSON: page/chapter + start/end offsets
    color: HighlightColor | None = None
    note_content: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Bookmark:
    """A saved reading position with an optional label."""

    id: str
    book_id: str
    position_data: str  # JSON: page or chapter + position
    label: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Comment:
    """A threaded comment attached to an annotation."""

    id: str
    annotation_id: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Collection:
    """A user-created group for organizing books."""

    id: str
    name: str
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Tag:
    """A label that can be associated with books, annotations, or vocabulary."""

    id: str
    name: str
    color: str | None = None


@dataclass
class ReadingHistory:
    """A record of when a book was accessed and the reading position at that time."""

    id: str
    book_id: str
    position_data: str  # JSON: page or chapter + scroll offset
    accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class VocabularyEntry:
    """A word saved to the user's vocabulary list from dictionary lookup."""

    id: str
    word: str
    definition: str
    mastery_level: MasteryLevel = MasteryLevel.NEW
    pronunciation: str | None = None
    part_of_speech: str | None = None
    example_sentence: str | None = None
    book_id: str | None = None
    position_data: str | None = None  # JSON: page/chapter + offset
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReviewCard:
    """A review card for spaced repetition of a vocabulary entry."""

    id: str
    vocabulary_id: str
    card_type: CardType = CardType.FLASHCARD
    # FSRS fields
    difficulty: float = 5.0
    stability: float = 0.4
    # SM2 fields
    ease_factor: float = 2.5
    repetitions: int = 0
    last_interval: float = 0.0
    # Common
    due_date: datetime = field(default_factory=lambda: datetime.now(UTC))
    algorithm: SRAlgorithm = SRAlgorithm.FSRS
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReviewLog:
    """A log entry for a single card review event."""

    id: str
    card_id: str
    rating: Rating
    elapsed_days: float
    scheduled_days: float
    review_duration_ms: float = 0.0
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph representing a book, annotation, vocabulary, or note."""

    id: str
    entity_type: str  # "book" | "annotation" | "vocabulary" | "note"
    entity_id: str
    label: str


@dataclass
class KnowledgeLink:
    """A link between two knowledge graph nodes."""

    id: str
    source_node_id: str
    target_node_id: str
    link_type: str  # "backlink" | "tag_shared" | "same_book"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DictCache:
    """A cached dictionary lookup result."""

    id: str
    word: str
    language: str
    source: str  # "oxford" | "cambridge" | "stardict" | "wiktionary"
    entry_json: str  # Full dictionary entry as JSON
    cached_at: datetime = field(default_factory=lambda: datetime.now(UTC))
