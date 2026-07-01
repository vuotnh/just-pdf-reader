"""Startup migration check for Alembic schema migrations.

Provides a function to auto-run `alembic upgrade head` on application startup,
ensuring the database schema is always up-to-date without manual intervention.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect

logger = logging.getLogger(__name__)

# Project root where alembic.ini lives
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _get_alembic_config(db_url: str | None = None) -> Config:
    """Build an Alembic Config pointing to the project's alembic.ini.

    Args:
        db_url: Optional SQLAlchemy database URL override.
                If provided, sets sqlalchemy.url in the config so
                migrations target the correct database.

    Returns:
        A configured Alembic Config instance.
    """
    ini_path = _PROJECT_ROOT / "alembic.ini"
    config = Config(str(ini_path))

    # Ensure script_location is resolved as an absolute path
    config.set_main_option(
        "script_location", str(_PROJECT_ROOT / "migrations")
    )

    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

    return config


def get_current_revision(engine: Engine) -> str | None:
    """Get the current Alembic revision of the database.

    Args:
        engine: SQLAlchemy engine connected to the target database.

    Returns:
        The current revision string, or None if no migrations have been applied.
    """
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def check_and_run_migrations(engine: Engine) -> None:
    """Check and apply any pending Alembic migrations.

    This function is designed to be called during application startup.
    It compares the current database revision to the latest available
    migration and runs `alembic upgrade head` if needed.

    If the database is brand new (no alembic_version table), all
    migrations will be applied from the beginning.

    Args:
        engine: SQLAlchemy engine connected to the target database.

    Raises:
        Exception: Re-raises any Alembic or SQLAlchemy errors after logging.
    """
    db_url = str(engine.url)

    try:
        # Check if the alembic_version table exists
        inspector = inspect(engine)
        has_version_table = "alembic_version" in inspector.get_table_names()

        if has_version_table:
            current_rev = get_current_revision(engine)
            logger.info("Current database revision: %s", current_rev or "none")
        else:
            logger.info(
                "No alembic_version table found. Running all migrations."
            )

        # Run upgrade head — this is idempotent if already at head
        config = _get_alembic_config(db_url=db_url)
        command.upgrade(config, "head")

        # Log the resulting revision
        new_rev = get_current_revision(engine)
        logger.info("Database migrated to revision: %s", new_rev)

    except Exception:
        logger.exception("Failed to run database migrations")
        raise
