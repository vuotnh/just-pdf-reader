"""Unit tests for FTS5 virtual tables and sync triggers."""

import uuid

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

from src.infrastructure.database.models import (
    AnnotationModel,
    Base,
    BookModel,
    VocabularyEntryModel,
)
from src.infrastructure.database.fts import (
    ALL_FTS_DDL,
    ANNOTATIONS_FTS_DDL,
    BOOKS_FTS_DDL,
    VOCABULARY_FTS_DDL,
    create_fts_tables,
    rebuild_fts_index,
)


def _make_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def fts_engine():
    """Create an in-memory SQLite engine with ORM tables and FTS5 tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    # Create ORM tables first
    Base.metadata.create_all(engine)
    # Then create FTS virtual tables and triggers
    create_fts_tables(engine)

    return engine


@pytest.fixture()
def fts_session(fts_engine):
    """Provide a session with FTS tables available."""
    session_factory = sessionmaker(bind=fts_engine)
    session = session_factory()
    yield session
    session.rollback()
    session.close()


class TestFTSTableCreation:
    """Test that FTS5 virtual tables are correctly created."""

    def test_books_fts_table_exists(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='books_fts'")
            ).fetchone()
            assert result is not None

    def test_annotations_fts_table_exists(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='annotations_fts'")
            ).fetchone()
            assert result is not None

    def test_vocabulary_fts_table_exists(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='vocabulary_fts'")
            ).fetchone()
            assert result is not None

    def test_create_fts_tables_is_idempotent(self, fts_engine):
        """Calling create_fts_tables multiple times should not raise errors."""
        # Already called once in fixture, call again
        create_fts_tables(fts_engine)
        create_fts_tables(fts_engine)

        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='books_fts'")
            ).fetchone()
            assert result is not None


class TestFTSTriggers:
    """Test that FTS sync triggers fire correctly on INSERT, UPDATE, DELETE."""

    def test_trigger_exists_books_ai(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger' AND name='books_ai'")
            ).fetchone()
            assert result is not None

    def test_trigger_exists_books_au(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger' AND name='books_au'")
            ).fetchone()
            assert result is not None

    def test_trigger_exists_books_ad(self, fts_engine):
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger' AND name='books_ad'")
            ).fetchone()
            assert result is not None

    def test_book_insert_syncs_to_fts(self, fts_session):
        """Inserting a book should auto-populate books_fts via trigger."""
        book = BookModel(
            id=_make_id(),
            title="Python Mastery",
            author="John Doe",
            file_path="/books/python.pdf",
            file_hash="hash1",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        # Query the FTS table directly
        result = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH 'Python'")
        ).fetchall()
        assert len(result) == 1

    def test_book_insert_searchable_by_author(self, fts_session):
        """Inserted book should be searchable by author in FTS."""
        book = BookModel(
            id=_make_id(),
            title="Some Title",
            author="Jane Smith",
            file_path="/books/book.pdf",
            file_hash="hash2",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH 'Jane'")
        ).fetchall()
        assert len(result) == 1

    def test_book_update_syncs_to_fts(self, fts_session):
        """Updating a book title should update the FTS index."""
        book = BookModel(
            id=_make_id(),
            title="Old Title",
            author="Author",
            file_path="/books/update.pdf",
            file_hash="hash3",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        # Update the title
        book.title = "New Title"
        fts_session.flush()

        # Old title should not be found
        old_results = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH '\"Old Title\"'")
        ).fetchall()
        assert len(old_results) == 0

        # New title should be found
        new_results = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH '\"New Title\"'")
        ).fetchall()
        assert len(new_results) == 1

    def test_book_delete_removes_from_fts(self, fts_session):
        """Deleting a book should remove it from the FTS index."""
        book = BookModel(
            id=_make_id(),
            title="Deletable Book",
            author="Author",
            file_path="/books/delete.pdf",
            file_hash="hash4",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        # Verify it's in FTS
        result = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH 'Deletable'")
        ).fetchall()
        assert len(result) == 1

        # Delete the book
        fts_session.delete(book)
        fts_session.flush()

        # Verify it's gone from FTS
        result = fts_session.execute(
            text("SELECT * FROM books_fts WHERE books_fts MATCH 'Deletable'")
        ).fetchall()
        assert len(result) == 0

    def test_annotation_insert_syncs_to_fts(self, fts_session):
        """Inserting an annotation should auto-populate annotations_fts."""
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/books/ann.pdf",
            file_hash="hash5",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        ann = AnnotationModel(
            id=_make_id(),
            book_id=book.id,
            type="highlight",
            selected_text="important concept here",
            note_content="Remember this for the exam",
        )
        fts_session.add(ann)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM annotations_fts WHERE annotations_fts MATCH 'important'")
        ).fetchall()
        assert len(result) == 1

    def test_annotation_searchable_by_note_content(self, fts_session):
        """Annotation note_content should be searchable in FTS."""
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/books/ann2.pdf",
            file_hash="hash6",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        ann = AnnotationModel(
            id=_make_id(),
            book_id=book.id,
            type="note",
            selected_text="some text",
            note_content="mitochondria powerhouse cell",
        )
        fts_session.add(ann)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM annotations_fts WHERE annotations_fts MATCH 'mitochondria'")
        ).fetchall()
        assert len(result) == 1

    def test_annotation_delete_removes_from_fts(self, fts_session):
        """Deleting an annotation should remove it from annotations_fts."""
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/books/ann3.pdf",
            file_hash="hash7",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        ann = AnnotationModel(
            id=_make_id(),
            book_id=book.id,
            type="highlight",
            selected_text="unique annotation text xyz",
        )
        fts_session.add(ann)
        fts_session.flush()

        fts_session.delete(ann)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM annotations_fts WHERE annotations_fts MATCH 'xyz'")
        ).fetchall()
        assert len(result) == 0

    def test_vocabulary_insert_syncs_to_fts(self, fts_session):
        """Inserting a vocabulary entry should auto-populate vocabulary_fts."""
        book = BookModel(
            id=_make_id(),
            title="Book",
            file_path="/books/vocab.pdf",
            file_hash="hash8",
            format="pdf",
        )
        fts_session.add(book)
        fts_session.flush()

        vocab = VocabularyEntryModel(
            id=_make_id(),
            word="ephemeral",
            definition="lasting for a very short time",
            example_sentence="Fame is ephemeral.",
            book_id=book.id,
        )
        fts_session.add(vocab)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM vocabulary_fts WHERE vocabulary_fts MATCH 'ephemeral'")
        ).fetchall()
        assert len(result) == 1

    def test_vocabulary_searchable_by_definition(self, fts_session):
        """Vocabulary definition should be searchable in FTS."""
        vocab = VocabularyEntryModel(
            id=_make_id(),
            word="ubiquitous",
            definition="present everywhere simultaneously",
            example_sentence="Smartphones are ubiquitous.",
        )
        fts_session.add(vocab)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM vocabulary_fts WHERE vocabulary_fts MATCH 'everywhere'")
        ).fetchall()
        assert len(result) == 1

    def test_vocabulary_delete_removes_from_fts(self, fts_session):
        """Deleting a vocabulary entry should remove it from vocabulary_fts."""
        vocab = VocabularyEntryModel(
            id=_make_id(),
            word="transient",
            definition="not permanent",
            example_sentence="A transient feeling.",
        )
        fts_session.add(vocab)
        fts_session.flush()

        fts_session.delete(vocab)
        fts_session.flush()

        result = fts_session.execute(
            text("SELECT * FROM vocabulary_fts WHERE vocabulary_fts MATCH 'transient'")
        ).fetchall()
        assert len(result) == 0


class TestRebuildFTSIndex:
    """Test the rebuild_fts_index utility function."""

    def test_rebuild_repopulates_books_fts(self, fts_engine):
        """rebuild_fts_index should correctly repopulate from source tables."""
        # Insert a book (trigger will populate FTS)
        with fts_engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO books (id, title, author, file_path, file_hash, format, is_favorite) "
                "VALUES ('b1', 'Rebuild Book', 'Rebuild Author', '/rebuild.pdf', 'h1', 'pdf', 0)"
            ))
            conn.commit()

        # Verify it's in FTS before rebuild
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM books_fts WHERE books_fts MATCH 'Rebuild'")
            ).fetchall()
            assert len(result) == 1

        # Rebuild should succeed without error and data remains searchable
        rebuild_fts_index(fts_engine)

        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM books_fts WHERE books_fts MATCH 'Rebuild'")
            ).fetchall()
            assert len(result) == 1

    def test_rebuild_repopulates_annotations_fts(self, fts_engine):
        """rebuild_fts_index should correctly repopulate annotations_fts."""
        with fts_engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO books (id, title, author, file_path, file_hash, format, is_favorite) "
                "VALUES ('b2', 'Book', 'Author', '/book2.pdf', 'h2', 'pdf', 0)"
            ))
            conn.execute(text(
                "INSERT INTO annotations (id, book_id, type, selected_text, note_content) "
                "VALUES ('a1', 'b2', 'highlight', 'rebuild annotation text', 'rebuild note')"
            ))
            conn.commit()

        # Rebuild should succeed
        rebuild_fts_index(fts_engine)

        # Verify searchable after rebuild
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM annotations_fts WHERE annotations_fts MATCH 'rebuild'")
            ).fetchall()
            assert len(result) == 1

    def test_rebuild_repopulates_vocabulary_fts(self, fts_engine):
        """rebuild_fts_index should correctly repopulate vocabulary_fts."""
        with fts_engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO vocabulary_entries (id, word, definition, example_sentence) "
                "VALUES ('v1', 'serendipity', 'happy accident', 'Found by serendipity.')"
            ))
            conn.commit()

        # Rebuild should succeed
        rebuild_fts_index(fts_engine)

        # Verify searchable after rebuild
        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM vocabulary_fts WHERE vocabulary_fts MATCH 'serendipity'")
            ).fetchall()
            assert len(result) == 1

    def test_rebuild_is_idempotent(self, fts_engine):
        """Calling rebuild multiple times should not cause errors."""
        with fts_engine.connect() as conn:
            conn.execute(text(
                "INSERT INTO books (id, title, author, file_path, file_hash, format, is_favorite) "
                "VALUES ('b3', 'Idempotent Book', 'Author', '/idemp.pdf', 'h3', 'pdf', 0)"
            ))
            conn.commit()

        rebuild_fts_index(fts_engine)
        rebuild_fts_index(fts_engine)
        rebuild_fts_index(fts_engine)

        with fts_engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM books_fts WHERE books_fts MATCH 'Idempotent'")
            ).fetchall()
            assert len(result) == 1
