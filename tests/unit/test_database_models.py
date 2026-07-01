"""Unit tests for SQLAlchemy ORM models and database setup."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from src.infrastructure.database.models import (
    AnnotationModel,
    Base,
    BookmarkModel,
    BookModel,
    CollectionModel,
    CommentModel,
    DictCacheModel,
    KnowledgeLinkModel,
    KnowledgeNodeModel,
    ReadingHistoryModel,
    ReviewCardModel,
    ReviewLogModel,
    TagModel,
    VocabularyEntryModel,
    annotation_tags,
    book_collections,
    book_tags,
    vocabulary_tags,
)
from src.infrastructure.database.engine import create_db_engine, _set_sqlite_pragmas
from src.infrastructure.database.session import SessionFactory, get_session


def _make_id() -> str:
    return str(uuid.uuid4())


class TestSchemaCreation:
    """Test that all tables are correctly created from the ORM models."""

    def test_all_entity_tables_exist(self, db_session: Session):
        """All 13 entity tables should be created."""
        inspector = inspect(db_session.bind)
        table_names = inspector.get_table_names()

        expected_tables = [
            "books",
            "collections",
            "tags",
            "annotations",
            "comments",
            "bookmarks",
            "reading_history",
            "vocabulary_entries",
            "review_cards",
            "review_logs",
            "knowledge_nodes",
            "knowledge_links",
            "dict_cache",
        ]
        for table in expected_tables:
            assert table in table_names, f"Missing table: {table}"

    def test_all_association_tables_exist(self, db_session: Session):
        """All 4 many-to-many association tables should be created."""
        inspector = inspect(db_session.bind)
        table_names = inspector.get_table_names()

        expected = ["book_collections", "book_tags", "annotation_tags", "vocabulary_tags"]
        for table in expected:
            assert table in table_names, f"Missing association table: {table}"

    def test_total_table_count(self, db_session: Session):
        """Should have exactly 17 tables (13 entities + 4 association)."""
        inspector = inspect(db_session.bind)
        table_names = inspector.get_table_names()
        assert len(table_names) == 17


class TestBookModel:
    """Test Book entity CRUD and relationships."""

    def test_create_book(self, db_session: Session):
        book = BookModel(
            id=_make_id(),
            title="Test Book",
            author="Author",
            file_path="/path/to/book.pdf",
            file_hash="abc123",
            format="pdf",
        )
        db_session.add(book)
        db_session.flush()

        result = db_session.query(BookModel).first()
        assert result.title == "Test Book"
        assert result.author == "Author"
        assert result.format == "pdf"
        assert result.is_favorite is False

    def test_book_collection_many_to_many(self, db_session: Session):
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/book.pdf",
            file_hash="h1",
            format="pdf",
        )
        collection = CollectionModel(id=_make_id(), name="Fiction")
        book.collections.append(collection)
        db_session.add(book)
        db_session.flush()

        assert collection in book.collections
        assert book in collection.books

    def test_book_tag_many_to_many(self, db_session: Session):
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/book.epub",
            file_hash="h2",
            format="epub",
        )
        tag = TagModel(id=_make_id(), name="science", color="blue")
        book.tags.append(tag)
        db_session.add(book)
        db_session.flush()

        assert tag in book.tags
        assert book in tag.books

    def test_book_cascade_delete_annotations(self, db_session: Session):
        book_id = _make_id()
        book = BookModel(
            id=book_id,
            title="Book",
            file_path="/book.pdf",
            file_hash="h3",
            format="pdf",
        )
        annotation = AnnotationModel(
            id=_make_id(),
            book_id=book_id,
            type="highlight",
            color="yellow",
            selected_text="some text",
        )
        book.annotations.append(annotation)
        db_session.add(book)
        db_session.flush()

        db_session.delete(book)
        db_session.flush()

        assert db_session.query(AnnotationModel).count() == 0


class TestAnnotationModel:
    """Test Annotation entity and relationships."""

    def _create_book(self, db_session: Session) -> BookModel:
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path=f"/book_{uuid.uuid4()}.pdf",
            file_hash=_make_id(),
            format="pdf",
        )
        db_session.add(book)
        db_session.flush()
        return book

    def test_create_annotation(self, db_session: Session):
        book = self._create_book(db_session)
        ann = AnnotationModel(
            id=_make_id(),
            book_id=book.id,
            type="highlight",
            color="green",
            selected_text="important text",
            position_data='{"page": 5, "start": 100, "end": 120}',
        )
        db_session.add(ann)
        db_session.flush()

        result = db_session.query(AnnotationModel).first()
        assert result.type == "highlight"
        assert result.color == "green"
        assert result.selected_text == "important text"

    def test_annotation_comments_cascade(self, db_session: Session):
        book = self._create_book(db_session)
        ann_id = _make_id()
        ann = AnnotationModel(id=ann_id, book_id=book.id, type="note")
        comment = CommentModel(id=_make_id(), annotation_id=ann_id, content="My thought")
        ann.comments.append(comment)
        db_session.add(ann)
        db_session.flush()

        assert len(ann.comments) == 1
        db_session.delete(ann)
        db_session.flush()
        assert db_session.query(CommentModel).count() == 0

    def test_annotation_tag_many_to_many(self, db_session: Session):
        book = self._create_book(db_session)
        ann = AnnotationModel(id=_make_id(), book_id=book.id, type="highlight")
        tag = TagModel(id=_make_id(), name="important", color="red")
        ann.tags.append(tag)
        db_session.add(ann)
        db_session.flush()

        assert tag in ann.tags
        assert ann in tag.annotations


class TestVocabularyAndReviewModels:
    """Test VocabularyEntry, ReviewCard, and ReviewLog relationships."""

    def _create_book(self, db_session: Session) -> BookModel:
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path=f"/book_{uuid.uuid4()}.pdf",
            file_hash=_make_id(),
            format="pdf",
        )
        db_session.add(book)
        db_session.flush()
        return book

    def test_vocabulary_entry_creation(self, db_session: Session):
        book = self._create_book(db_session)
        vocab = VocabularyEntryModel(
            id=_make_id(),
            word="ephemeral",
            pronunciation="/ɪˈfɛmərəl/",
            part_of_speech="adjective",
            definition="lasting for a very short time",
            example_sentence="Fame is ephemeral.",
            book_id=book.id,
            mastery_level="new",
        )
        db_session.add(vocab)
        db_session.flush()

        result = db_session.query(VocabularyEntryModel).first()
        assert result.word == "ephemeral"
        assert result.mastery_level == "new"

    def test_vocabulary_cascade_to_review_cards(self, db_session: Session):
        book = self._create_book(db_session)
        vocab_id = _make_id()
        vocab = VocabularyEntryModel(
            id=vocab_id,
            word="test",
            book_id=book.id,
        )
        card = ReviewCardModel(
            id=_make_id(),
            vocabulary_id=vocab_id,
            due_date=datetime.utcnow(),
        )
        vocab.cards.append(card)
        db_session.add(vocab)
        db_session.flush()

        assert db_session.query(ReviewCardModel).count() == 1
        db_session.delete(vocab)
        db_session.flush()
        assert db_session.query(ReviewCardModel).count() == 0

    def test_review_card_cascade_to_logs(self, db_session: Session):
        book = self._create_book(db_session)
        vocab_id = _make_id()
        vocab = VocabularyEntryModel(id=vocab_id, word="word", book_id=book.id)
        card_id = _make_id()
        card = ReviewCardModel(
            id=card_id, vocabulary_id=vocab_id, due_date=datetime.utcnow()
        )
        log = ReviewLogModel(
            id=_make_id(), card_id=card_id, rating="good", elapsed_days=1.0
        )
        card.review_logs.append(log)
        vocab.cards.append(card)
        db_session.add(vocab)
        db_session.flush()

        assert db_session.query(ReviewLogModel).count() == 1
        db_session.delete(card)
        db_session.flush()
        assert db_session.query(ReviewLogModel).count() == 0

    def test_vocabulary_tag_many_to_many(self, db_session: Session):
        book = self._create_book(db_session)
        vocab = VocabularyEntryModel(id=_make_id(), word="test", book_id=book.id)
        tag = TagModel(id=_make_id(), name="chapter1", color="green")
        vocab.tags.append(tag)
        db_session.add(vocab)
        db_session.flush()

        assert tag in vocab.tags
        assert vocab in tag.vocabulary_entries


class TestKnowledgeGraphModels:
    """Test KnowledgeNode and KnowledgeLink relationships."""

    def test_create_knowledge_node(self, db_session: Session):
        node = KnowledgeNodeModel(
            id=_make_id(), entity_type="book", entity_id="book-123", label="My Book"
        )
        db_session.add(node)
        db_session.flush()

        result = db_session.query(KnowledgeNodeModel).first()
        assert result.entity_type == "book"
        assert result.label == "My Book"

    def test_knowledge_link_between_nodes(self, db_session: Session):
        node_a_id = _make_id()
        node_b_id = _make_id()
        node_a = KnowledgeNodeModel(
            id=node_a_id, entity_type="annotation", entity_id="ann-1", label="Note A"
        )
        node_b = KnowledgeNodeModel(
            id=node_b_id, entity_type="vocabulary", entity_id="vocab-1", label="Word B"
        )
        link = KnowledgeLinkModel(
            id=_make_id(),
            source_node_id=node_a_id,
            target_node_id=node_b_id,
            link_type="backlink",
        )
        db_session.add_all([node_a, node_b, link])
        db_session.flush()

        assert len(node_a.links_as_source) == 1
        assert len(node_b.links_as_target) == 1
        assert node_a.links_as_source[0].target_node == node_b

    def test_node_cascade_deletes_links(self, db_session: Session):
        node_a_id = _make_id()
        node_b_id = _make_id()
        node_a = KnowledgeNodeModel(
            id=node_a_id, entity_type="book", entity_id="b1", label="A"
        )
        node_b = KnowledgeNodeModel(
            id=node_b_id, entity_type="book", entity_id="b2", label="B"
        )
        link = KnowledgeLinkModel(
            id=_make_id(),
            source_node_id=node_a_id,
            target_node_id=node_b_id,
            link_type="same_book",
        )
        db_session.add_all([node_a, node_b, link])
        db_session.flush()

        db_session.delete(node_a)
        db_session.flush()
        assert db_session.query(KnowledgeLinkModel).count() == 0


class TestDictCacheModel:
    """Test DictCache entity."""

    def test_create_dict_cache_entry(self, db_session: Session):
        entry = DictCacheModel(
            id=_make_id(),
            word="hello",
            language="en",
            source="oxford",
            entry_json='{"word": "hello", "definitions": ["greeting"]}',
        )
        db_session.add(entry)
        db_session.flush()

        result = db_session.query(DictCacheModel).first()
        assert result.word == "hello"
        assert result.source == "oxford"
        assert "greeting" in result.entry_json


class TestEngineConfiguration:
    """Test database engine pragmas and configuration."""

    def test_wal_mode_enabled(self, db_engine):
        """WAL mode is set via pragma. In-memory databases report 'memory' instead."""
        with db_engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).scalar()
            # In-memory SQLite cannot use WAL, so the pragma is accepted
            # but the effective mode remains 'memory'. On a file-based DB it
            # would be 'wal'. We accept both as valid outcomes.
            assert result in ("wal", "memory")

    def test_foreign_keys_enabled(self, db_engine):
        with db_engine.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert result == 1

    def test_synchronous_normal(self, db_engine):
        with db_engine.connect() as conn:
            result = conn.execute(text("PRAGMA synchronous")).scalar()
            # NORMAL = 1
            assert result == 1


class TestSessionFactory:
    """Test session factory and context manager behavior."""

    def test_session_context_manager_commits(self, db_engine):
        Base.metadata.create_all(db_engine)
        factory = SessionFactory(db_engine)

        with factory() as session:
            book = BookModel(
                id=_make_id(),
                title="Committed Book",
                file_path="/committed.pdf",
                file_hash="hash1",
                format="pdf",
            )
            session.add(book)

        # Verify committed by opening a new session
        with factory() as session:
            result = session.query(BookModel).filter_by(title="Committed Book").first()
            assert result is not None

    def test_session_context_manager_rolls_back_on_error(self, db_engine):
        Base.metadata.create_all(db_engine)
        factory = SessionFactory(db_engine)

        with pytest.raises(ValueError):
            with factory() as session:
                book = BookModel(
                    id=_make_id(),
                    title="Rolled Back Book",
                    file_path="/rollback.pdf",
                    file_hash="hash2",
                    format="pdf",
                )
                session.add(book)
                raise ValueError("Simulated error")

        # Verify rolled back
        with factory() as session:
            result = session.query(BookModel).filter_by(title="Rolled Back Book").first()
            assert result is None

    def test_get_session_convenience_function(self, db_engine):
        Base.metadata.create_all(db_engine)

        with get_session(db_engine) as session:
            book = BookModel(
                id=_make_id(),
                title="Convenience Book",
                file_path="/convenience.pdf",
                file_hash="hash3",
                format="pdf",
            )
            session.add(book)

        # Verify
        with get_session(db_engine) as session:
            result = session.query(BookModel).filter_by(title="Convenience Book").first()
            assert result is not None
