"""Unit tests for the Alembic migration infrastructure."""

import pytest
from sqlalchemy import create_engine, event, inspect, text

from src.infrastructure.database.migrations import (
    _get_alembic_config,
    check_and_run_migrations,
    get_current_revision,
)


@pytest.fixture()
def tmp_db_engine(tmp_path):
    """Create a temporary SQLite database engine for migration tests."""
    db_path = tmp_path / "test_migrations.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


class TestGetAlembicConfig:
    """Tests for _get_alembic_config helper."""

    def test_returns_config_with_script_location(self):
        config = _get_alembic_config()
        script_location = config.get_main_option("script_location")
        assert script_location is not None
        assert "migrations" in script_location

    def test_overrides_db_url_when_provided(self):
        url = "sqlite:///test.db"
        config = _get_alembic_config(db_url=url)
        assert config.get_main_option("sqlalchemy.url") == url


class TestGetCurrentRevision:
    """Tests for get_current_revision."""

    def test_returns_none_for_fresh_database(self, tmp_db_engine):
        """A new database with no alembic_version table returns None."""
        revision = get_current_revision(tmp_db_engine)
        assert revision is None


class TestCheckAndRunMigrations:
    """Tests for check_and_run_migrations."""

    def test_applies_migrations_to_fresh_database(self, tmp_db_engine):
        """Running migrations on a fresh DB creates all tables."""
        check_and_run_migrations(tmp_db_engine)

        inspector = inspect(tmp_db_engine)
        table_names = inspector.get_table_names()

        # Core tables from the initial migration should exist
        assert "books" in table_names
        assert "annotations" in table_names
        assert "vocabulary_entries" in table_names
        assert "review_cards" in table_names
        assert "knowledge_nodes" in table_names
        assert "dict_cache" in table_names
        assert "alembic_version" in table_names

    def test_sets_revision_after_migration(self, tmp_db_engine):
        """After running migrations, current revision is not None."""
        check_and_run_migrations(tmp_db_engine)

        revision = get_current_revision(tmp_db_engine)
        assert revision is not None
        assert revision == "0001"

    def test_idempotent_on_repeated_calls(self, tmp_db_engine):
        """Running migrations twice does not raise or corrupt the database."""
        check_and_run_migrations(tmp_db_engine)
        check_and_run_migrations(tmp_db_engine)

        revision = get_current_revision(tmp_db_engine)
        assert revision == "0001"

    def test_all_association_tables_created(self, tmp_db_engine):
        """All many-to-many association tables are created by migration."""
        check_and_run_migrations(tmp_db_engine)

        inspector = inspect(tmp_db_engine)
        table_names = inspector.get_table_names()

        assert "book_collections" in table_names
        assert "book_tags" in table_names
        assert "annotation_tags" in table_names
        assert "vocabulary_tags" in table_names
