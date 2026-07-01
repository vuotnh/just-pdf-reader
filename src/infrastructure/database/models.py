"""SQLAlchemy ORM models for the AI Ebook Reader platform.

All models correspond to entities in the ER diagram from the design document.
Association tables implement many-to-many relationships:
  - book_collections: Book <-> Collection
  - book_tags: Book <-> Tag
  - annotation_tags: Annotation <-> Tag
  - vocabulary_tags: VocabularyEntry <-> Tag
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ---------------------------------------------------------------------------
# Association tables (many-to-many)
# ---------------------------------------------------------------------------

book_collections = Table(
    "book_collections",
    Base.metadata,
    Column("book_id", String, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "collection_id",
        String,
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

book_tags = Table(
    "book_tags",
    Base.metadata,
    Column("book_id", String, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

annotation_tags = Table(
    "annotation_tags",
    Base.metadata,
    Column(
        "annotation_id",
        String,
        ForeignKey("annotations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

vocabulary_tags = Table(
    "vocabulary_tags",
    Base.metadata,
    Column(
        "vocabulary_id",
        String,
        ForeignKey("vocabulary_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", String, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------------------
# Entity models
# ---------------------------------------------------------------------------


class BookModel(Base):
    """A book (PDF, EPUB, or AZW3) imported into the library."""

    __tablename__ = "books"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    author = Column(String)
    publisher = Column(String)
    language = Column(String)
    page_count = Column(Integer)
    file_path = Column(String, nullable=False, unique=True)
    file_hash = Column(String, nullable=False)
    format = Column(String, nullable=False)  # "pdf", "epub", "azw3"
    cover_image = Column(Text)  # Base64 encoded thumbnail
    is_favorite = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    annotations = relationship(
        "AnnotationModel", back_populates="book", cascade="all, delete-orphan"
    )
    bookmarks = relationship(
        "BookmarkModel", back_populates="book", cascade="all, delete-orphan"
    )
    reading_history = relationship(
        "ReadingHistoryModel", back_populates="book", cascade="all, delete-orphan"
    )
    vocabulary_entries = relationship(
        "VocabularyEntryModel", back_populates="book", cascade="all, delete-orphan"
    )
    collections = relationship(
        "CollectionModel", secondary=book_collections, back_populates="books"
    )
    tags = relationship("TagModel", secondary=book_tags, back_populates="books")


class CollectionModel(Base):
    """A user-defined collection for organizing books."""

    __tablename__ = "collections"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    books = relationship(
        "BookModel", secondary=book_collections, back_populates="collections"
    )


class TagModel(Base):
    """A tag that can be applied to books, annotations, and vocabulary."""

    __tablename__ = "tags"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String)

    # Relationships
    books = relationship("BookModel", secondary=book_tags, back_populates="tags")
    annotations = relationship(
        "AnnotationModel", secondary=annotation_tags, back_populates="tags"
    )
    vocabulary_entries = relationship(
        "VocabularyEntryModel", secondary=vocabulary_tags, back_populates="tags"
    )


class AnnotationModel(Base):
    """An annotation (highlight, underline, note, comment) on book content."""

    __tablename__ = "annotations"

    id = Column(String, primary_key=True)
    book_id = Column(String, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # "highlight", "underline", "note", "comment"
    color = Column(String)  # "yellow", "green", "blue", "pink", "orange"
    selected_text = Column(Text)
    note_content = Column(Text)
    position_data = Column(Text)  # JSON: page/chapter + start/end offsets
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    book = relationship("BookModel", back_populates="annotations")
    comments = relationship(
        "CommentModel", back_populates="annotation", cascade="all, delete-orphan"
    )
    tags = relationship(
        "TagModel", secondary=annotation_tags, back_populates="annotations"
    )



class CommentModel(Base):
    """A comment attached to an annotation."""

    __tablename__ = "comments"

    id = Column(String, primary_key=True)
    annotation_id = Column(
        String, ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    annotation = relationship("AnnotationModel", back_populates="comments")


class BookmarkModel(Base):
    """A bookmark at a specific location in a book."""

    __tablename__ = "bookmarks"

    id = Column(String, primary_key=True)
    book_id = Column(String, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    label = Column(String)
    position_data = Column(Text)  # JSON: page or chapter+position
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    book = relationship("BookModel", back_populates="bookmarks")


class ReadingHistoryModel(Base):
    """A reading history entry recording when and where a book was accessed."""

    __tablename__ = "reading_history"

    id = Column(String, primary_key=True)
    book_id = Column(String, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    position_data = Column(Text)  # JSON: reading position
    accessed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    book = relationship("BookModel", back_populates="reading_history")


class VocabularyEntryModel(Base):
    """A vocabulary word saved from dictionary lookup during reading."""

    __tablename__ = "vocabulary_entries"

    id = Column(String, primary_key=True)
    word = Column(String, nullable=False)
    pronunciation = Column(String)
    part_of_speech = Column(String)
    definition = Column(Text)
    example_sentence = Column(Text)
    book_id = Column(String, ForeignKey("books.id", ondelete="SET NULL"))
    position_data = Column(Text)  # JSON: page/chapter + position
    mastery_level = Column(String, default="new")  # "new", "learning", "reviewing", "mastered"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    book = relationship("BookModel", back_populates="vocabulary_entries")
    cards = relationship(
        "ReviewCardModel", back_populates="vocabulary", cascade="all, delete-orphan"
    )
    tags = relationship(
        "TagModel", secondary=vocabulary_tags, back_populates="vocabulary_entries"
    )


class ReviewCardModel(Base):
    """A review card for spaced repetition of a vocabulary entry."""

    __tablename__ = "review_cards"

    id = Column(String, primary_key=True)
    vocabulary_id = Column(
        String, ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), nullable=False
    )
    card_type = Column(String, default="flashcard")  # "flashcard", "cloze", "typing", "mcq"
    # FSRS fields
    difficulty = Column(Float, default=5.0)
    stability = Column(Float, default=0.4)
    # SM2 fields
    ease_factor = Column(Float, default=2.5)
    repetitions = Column(Integer, default=0)
    last_interval = Column(Float, default=0.0)
    # Common
    due_date = Column(DateTime, nullable=False)
    algorithm = Column(String, default="fsrs")  # "sm2" or "fsrs"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    vocabulary = relationship("VocabularyEntryModel", back_populates="cards")
    review_logs = relationship(
        "ReviewLogModel", back_populates="card", cascade="all, delete-orphan"
    )


class ReviewLogModel(Base):
    """A log entry recording a single review event for a card."""

    __tablename__ = "review_logs"

    id = Column(String, primary_key=True)
    card_id = Column(
        String, ForeignKey("review_cards.id", ondelete="CASCADE"), nullable=False
    )
    rating = Column(String, nullable=False)  # "again", "hard", "good", "easy"
    elapsed_days = Column(Float)
    scheduled_days = Column(Float)
    review_duration_ms = Column(Float)
    reviewed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    card = relationship("ReviewCardModel", back_populates="review_logs")


class KnowledgeNodeModel(Base):
    """A node in the knowledge graph representing a book, annotation, vocabulary, or note."""

    __tablename__ = "knowledge_nodes"

    id = Column(String, primary_key=True)
    entity_type = Column(String, nullable=False)  # "book", "annotation", "vocabulary", "note"
    entity_id = Column(String, nullable=False)
    label = Column(String)

    # Relationships
    links_as_source = relationship(
        "KnowledgeLinkModel",
        foreign_keys="KnowledgeLinkModel.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    links_as_target = relationship(
        "KnowledgeLinkModel",
        foreign_keys="KnowledgeLinkModel.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class KnowledgeLinkModel(Base):
    """A link between two knowledge graph nodes."""

    __tablename__ = "knowledge_links"

    id = Column(String, primary_key=True)
    source_node_id = Column(
        String, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id = Column(
        String, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False
    )
    link_type = Column(String, nullable=False)  # "backlink", "tag_shared", "same_book"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_node = relationship(
        "KnowledgeNodeModel",
        foreign_keys=[source_node_id],
        back_populates="links_as_source",
    )
    target_node = relationship(
        "KnowledgeNodeModel",
        foreign_keys=[target_node_id],
        back_populates="links_as_target",
    )


class DictCacheModel(Base):
    """A cached dictionary lookup result."""

    __tablename__ = "dict_cache"

    id = Column(String, primary_key=True)
    word = Column(String, nullable=False)
    language = Column(String)
    source = Column(String)  # "oxford", "cambridge", "stardict", "wiktionary"
    entry_json = Column(Text, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow)
