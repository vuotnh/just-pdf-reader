"""SQLite-based dictionary cache using the DictCacheModel.

Provides O(1) lookup by word+language key for previously resolved definitions.
Implements the DictionarySource protocol for integration with the lookup chain.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.infrastructure.database.models import DictCacheModel
from src.infrastructure.dictionary.lookup_chain import DictEntry

logger = logging.getLogger(__name__)


class DictCacheRepository:
    """SQLite-backed dictionary cache.

    Uses the DictCacheModel table to store and retrieve previously
    looked-up word definitions, keyed by (word, language).
    """

    def __init__(self, session: Session) -> None:
        """Initialize with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy session for database operations.
        """
        self._session = session

    @property
    def source_name(self) -> str:
        """Identifier for this source in the lookup chain."""
        return "cache"

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in the local cache.

        Args:
            word: The word to look up (should be normalized/lowercased).
            language: Language code for the lookup.

        Returns:
            DictEntry if found in cache, None otherwise.
        """
        record = (
            self._session.query(DictCacheModel)
            .filter(
                DictCacheModel.word == word,
                DictCacheModel.language == language,
            )
            .first()
        )

        if record is None:
            return None

        try:
            entry = DictEntry.from_json(record.entry_json)
            entry.source = "cache"
            return entry
        except Exception:
            logger.exception("Failed to deserialize cached entry for '%s'", word)
            return None

    def store(self, entry: DictEntry, language: str = "en") -> None:
        """Store a dictionary entry in the cache.

        If an entry for the same word+language already exists, it is updated.

        Args:
            entry: The DictEntry to cache.
            language: Language code for the cache key.
        """
        existing = (
            self._session.query(DictCacheModel)
            .filter(
                DictCacheModel.word == entry.word,
                DictCacheModel.language == language,
            )
            .first()
        )

        json_data = entry.to_json()

        if existing:
            existing.entry_json = json_data
            existing.source = entry.source
            existing.cached_at = datetime.now(UTC)
        else:
            record = DictCacheModel(
                id=str(uuid.uuid4()),
                word=entry.word,
                language=language,
                source=entry.source,
                entry_json=json_data,
                cached_at=datetime.now(UTC),
            )
            self._session.add(record)

        self._session.commit()

    def invalidate(self, word: str, language: str = "en") -> None:
        """Remove a cached entry.

        Args:
            word: The word to remove from cache.
            language: Language code for the cache key.
        """
        self._session.query(DictCacheModel).filter(
            DictCacheModel.word == word,
            DictCacheModel.language == language,
        ).delete()
        self._session.commit()

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._session.query(DictCacheModel).delete()
        self._session.commit()
