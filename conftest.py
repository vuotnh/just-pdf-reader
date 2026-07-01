"""Root conftest.py with shared fixtures and Hypothesis profiles."""

import os
import pytest
from hypothesis import settings, HealthCheck, Phase
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Ensure Qt uses offscreen rendering for headless test environments
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
)

settings.register_profile(
    "dev",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile(
    "quick",
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.load_profile("dev")

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine with WAL-like pragmas enabled."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.close()

    return engine


@pytest.fixture()
def db_session(db_engine) -> Session:
    """Provide a transactional database session scoped to a single test.

    Creates all tables from the ORM Base metadata before yielding
    and rolls back after the test completes.
    """
    # Import here to avoid circular imports during collection
    try:
        from src.infrastructure.database.models import Base

        Base.metadata.create_all(db_engine)
    except ImportError:
        # Models not yet created - allow tests that don't need DB to pass
        pass

    session_factory = sessionmaker(bind=db_engine)
    session = session_factory()

    yield session

    session.rollback()
    session.close()
