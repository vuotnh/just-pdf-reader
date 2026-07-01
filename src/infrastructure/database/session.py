"""Database session factory and context manager.

Provides a session factory and a convenient context manager for
transactional database access.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


class SessionFactory:
    """Factory for creating database sessions.

    Wraps SQLAlchemy's sessionmaker to provide a consistent interface
    for obtaining transactional sessions throughout the application.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine)

    @contextmanager
    def __call__(self) -> Generator[Session, None, None]:
        """Create a session context that commits on success or rolls back on error.

        Usage:
            factory = SessionFactory(engine)
            with factory() as session:
                session.add(entity)
                # auto-commits if no exception
        """
        session: Session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_session(self) -> Session:
        """Create a raw session without automatic transaction management.

        The caller is responsible for committing, rolling back, and closing.
        """
        return self._session_factory()


@contextmanager
def get_session(engine: Engine) -> Generator[Session, None, None]:
    """Convenience context manager for one-off session usage.

    Args:
        engine: The SQLAlchemy engine to bind the session to.

    Yields:
        A Session instance that auto-commits on success.
    """
    factory = SessionFactory(engine)
    with factory() as session:
        yield session
