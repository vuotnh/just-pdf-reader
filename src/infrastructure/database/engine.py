"""Database engine creation and configuration.

Configures SQLite with WAL mode, foreign key enforcement, and
synchronous=NORMAL for a balance of safety and performance.
"""

from pathlib import Path

from sqlalchemy import Engine, event, create_engine


def get_default_db_path() -> Path:
    """Return the default database file path.

    The database is stored in ~/.ai-ebook-reader/data/library.db
    """
    db_dir = Path.home() / ".ai-ebook-reader" / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "library.db"


def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Set SQLite pragmas on every new connection.

    - foreign_keys=ON: enforce referential integrity
    - journal_mode=WAL: write-ahead logging for crash recovery and concurrency
    - synchronous=NORMAL: balance between safety and performance
    - auto_vacuum=INCREMENTAL: reclaim space without full vacuum
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA auto_vacuum = INCREMENTAL")
    cursor.close()


def create_db_engine(db_path: Path | None = None, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine configured for SQLite.

    Args:
        db_path: Path to the SQLite database file. If None, uses the default path.
        echo: If True, log all SQL statements (useful for debugging).

    Returns:
        A configured SQLAlchemy Engine instance.
    """
    if db_path is None:
        db_path = get_default_db_path()

    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=echo)

    # Register the pragma listener for every new connection
    event.listen(engine, "connect", _set_sqlite_pragmas)

    return engine
