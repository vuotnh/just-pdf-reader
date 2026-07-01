"""Database infrastructure package for AI Ebook Reader."""

from src.infrastructure.database.engine import create_db_engine, get_default_db_path
from src.infrastructure.database.fts import create_fts_tables, rebuild_fts_index
from src.infrastructure.database.migrations import check_and_run_migrations
from src.infrastructure.database.models import Base
from src.infrastructure.database.session import SessionFactory, get_session

__all__ = [
    "Base",
    "SessionFactory",
    "check_and_run_migrations",
    "create_db_engine",
    "create_fts_tables",
    "get_default_db_path",
    "get_session",
    "rebuild_fts_index",
]
