"""FTS5 virtual tables and sync triggers for full-text search.

Provides DDL for FTS5 virtual tables that index books, annotations, and
vocabulary entries. Includes triggers to keep the FTS index in sync on
INSERT, UPDATE, and DELETE operations, plus a utility to rebuild indexes
from existing data.

Requirements: 10.1, 10.6
"""

from sqlalchemy import Engine, text


# ---------------------------------------------------------------------------
# FTS5 Virtual Table DDL
# ---------------------------------------------------------------------------

BOOKS_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title, author,
    content='books',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

ANNOTATIONS_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS annotations_fts USING fts5(
    selected_text, note_content,
    content='annotations',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

VOCABULARY_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS vocabulary_fts USING fts5(
    word, definition, example_sentence,
    content='vocabulary_entries',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

# ---------------------------------------------------------------------------
# Sync Triggers DDL
# ---------------------------------------------------------------------------

# Books triggers
BOOKS_AFTER_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
    INSERT INTO books_fts(rowid, title, author)
    VALUES (new.rowid, new.title, COALESCE(new.author, ''));
END;
"""

BOOKS_AFTER_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, author)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.author, ''));
    INSERT INTO books_fts(rowid, title, author)
    VALUES (new.rowid, new.title, COALESCE(new.author, ''));
END;
"""

BOOKS_AFTER_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, author)
    VALUES ('delete', old.rowid, old.title, COALESCE(old.author, ''));
END;
"""

# Annotations triggers
ANNOTATIONS_AFTER_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS annotations_ai AFTER INSERT ON annotations BEGIN
    INSERT INTO annotations_fts(rowid, selected_text, note_content)
    VALUES (new.rowid, COALESCE(new.selected_text, ''), COALESCE(new.note_content, ''));
END;
"""

ANNOTATIONS_AFTER_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS annotations_au AFTER UPDATE ON annotations BEGIN
    INSERT INTO annotations_fts(annotations_fts, rowid, selected_text, note_content)
    VALUES ('delete', old.rowid, COALESCE(old.selected_text, ''), COALESCE(old.note_content, ''));
    INSERT INTO annotations_fts(rowid, selected_text, note_content)
    VALUES (new.rowid, COALESCE(new.selected_text, ''), COALESCE(new.note_content, ''));
END;
"""

ANNOTATIONS_AFTER_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS annotations_ad AFTER DELETE ON annotations BEGIN
    INSERT INTO annotations_fts(annotations_fts, rowid, selected_text, note_content)
    VALUES ('delete', old.rowid, COALESCE(old.selected_text, ''), COALESCE(old.note_content, ''));
END;
"""

# Vocabulary triggers
VOCABULARY_AFTER_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS vocabulary_ai AFTER INSERT ON vocabulary_entries BEGIN
    INSERT INTO vocabulary_fts(rowid, word, definition, example_sentence)
    VALUES (new.rowid, new.word, COALESCE(new.definition, ''), COALESCE(new.example_sentence, ''));
END;
"""

VOCABULARY_AFTER_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS vocabulary_au AFTER UPDATE ON vocabulary_entries BEGIN
    INSERT INTO vocabulary_fts(vocabulary_fts, rowid, word, definition, example_sentence)
    VALUES ('delete', old.rowid, old.word, COALESCE(old.definition, ''), COALESCE(old.example_sentence, ''));
    INSERT INTO vocabulary_fts(rowid, word, definition, example_sentence)
    VALUES (new.rowid, new.word, COALESCE(new.definition, ''), COALESCE(new.example_sentence, ''));
END;
"""

VOCABULARY_AFTER_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS vocabulary_ad AFTER DELETE ON vocabulary_entries BEGIN
    INSERT INTO vocabulary_fts(vocabulary_fts, rowid, word, definition, example_sentence)
    VALUES ('delete', old.rowid, old.word, COALESCE(old.definition, ''), COALESCE(old.example_sentence, ''));
END;
"""

# ---------------------------------------------------------------------------
# All DDL statements in execution order
# ---------------------------------------------------------------------------

ALL_FTS_DDL = [
    BOOKS_FTS_DDL,
    ANNOTATIONS_FTS_DDL,
    VOCABULARY_FTS_DDL,
    BOOKS_AFTER_INSERT_TRIGGER,
    BOOKS_AFTER_UPDATE_TRIGGER,
    BOOKS_AFTER_DELETE_TRIGGER,
    ANNOTATIONS_AFTER_INSERT_TRIGGER,
    ANNOTATIONS_AFTER_UPDATE_TRIGGER,
    ANNOTATIONS_AFTER_DELETE_TRIGGER,
    VOCABULARY_AFTER_INSERT_TRIGGER,
    VOCABULARY_AFTER_UPDATE_TRIGGER,
    VOCABULARY_AFTER_DELETE_TRIGGER,
]


def create_fts_tables(engine: Engine) -> None:
    """Create all FTS5 virtual tables and sync triggers.

    This function is idempotent — it uses IF NOT EXISTS for all DDL
    statements so it can be safely called multiple times.

    Args:
        engine: The SQLAlchemy engine connected to the SQLite database.
    """
    with engine.connect() as conn:
        for ddl in ALL_FTS_DDL:
            conn.execute(text(ddl))
        conn.commit()


def rebuild_fts_index(engine: Engine) -> None:
    """Rebuild all FTS5 indexes from existing data in source tables.

    Use this to re-populate the FTS indexes after bulk data import
    or if the indexes become out of sync. This uses the FTS5 'rebuild'
    command which is the correct way to rebuild content-sync tables.

    Args:
        engine: The SQLAlchemy engine connected to the SQLite database.
    """
    rebuild_statements = [
        "INSERT INTO books_fts(books_fts) VALUES('rebuild');",
        "INSERT INTO annotations_fts(annotations_fts) VALUES('rebuild');",
        "INSERT INTO vocabulary_fts(vocabulary_fts) VALUES('rebuild');",
    ]

    with engine.connect() as conn:
        for stmt in rebuild_statements:
            conn.execute(text(stmt))
        conn.commit()
