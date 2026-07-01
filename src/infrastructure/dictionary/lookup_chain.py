"""Dictionary lookup chain-of-responsibility implementation.

Defines the DictEntry normalized result and the DictionaryLookupChain
that orchestrates: cache → StarDict → online API (configurable priority).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class DictEntry:
    """Normalized dictionary entry returned by any lookup source.

    Attributes:
        word: The looked-up word.
        ipa: IPA pronunciation string (e.g. "/ˈhɛl.oʊ/").
        parts_of_speech: List of parts of speech with their definitions.
        examples: Example sentences demonstrating usage.
        synonyms: List of synonym words.
        source: Which source provided this entry (e.g. "cache", "stardict", "oxford").
        language: Language code (e.g. "en", "vi").
    """

    word: str
    ipa: str = ""
    parts_of_speech: list[PartOfSpeech] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    source: str = ""
    language: str = "en"

    def to_json(self) -> str:
        """Serialize entry to JSON string for caching."""
        return json.dumps(
            {
                "word": self.word,
                "ipa": self.ipa,
                "parts_of_speech": [
                    {"pos": p.pos, "definitions": p.definitions} for p in self.parts_of_speech
                ],
                "examples": self.examples,
                "synonyms": self.synonyms,
                "source": self.source,
                "language": self.language,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, json_str: str) -> DictEntry:
        """Deserialize entry from JSON string."""
        data = json.loads(json_str)
        parts = [
            PartOfSpeech(pos=p["pos"], definitions=p["definitions"])
            for p in data.get("parts_of_speech", [])
        ]
        return cls(
            word=data["word"],
            ipa=data.get("ipa", ""),
            parts_of_speech=parts,
            examples=data.get("examples", []),
            synonyms=data.get("synonyms", []),
            source=data.get("source", ""),
            language=data.get("language", "en"),
        )


@dataclass
class PartOfSpeech:
    """A part-of-speech entry with its definitions.

    Attributes:
        pos: Part of speech label (e.g. "noun", "verb", "adjective").
        definitions: List of definition strings for this part of speech.
    """

    pos: str
    definitions: list[str] = field(default_factory=list)


class DictionarySource(Protocol):
    """Protocol for a dictionary lookup source in the chain."""

    @property
    def source_name(self) -> str:
        """Unique identifier for this source (e.g. 'cache', 'stardict', 'oxford')."""
        ...

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word and return a DictEntry, or None if not found.

        Args:
            word: The word to look up.
            language: Language code for lookup context.

        Returns:
            DictEntry if found, None otherwise.
        """
        ...


class DictionaryLookupChain:
    """Chain-of-responsibility orchestrator for dictionary lookups.

    The chain is traversed in order. The first source to return a result wins.
    If the result comes from a non-cache source, the cache is populated.

    Default chain order: cache → StarDict → online APIs
    """

    def __init__(
        self,
        sources: list[DictionarySource] | None = None,
        cache_source: DictionarySource | None = None,
    ) -> None:
        """Initialize the lookup chain.

        Args:
            sources: Ordered list of dictionary sources to query.
                     The first source that returns a result wins.
            cache_source: The cache source used for populating on successful
                         lookup from non-cache sources. If None, caching is disabled.
        """
        self._sources: list[DictionarySource] = sources or []
        self._cache_source = cache_source

    @property
    def sources(self) -> list[DictionarySource]:
        """Return the current list of sources in chain order."""
        return list(self._sources)

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word through the chain of sources.

        Traverses sources in order. On a hit from a non-cache source,
        populates the cache for future lookups.

        Args:
            word: The word to look up.
            language: Language code for lookup context.

        Returns:
            DictEntry from the first source that has the word, or None.
        """
        normalized_word = word.strip().lower()
        if not normalized_word:
            return None

        for source in self._sources:
            try:
                entry = source.lookup(normalized_word, language)
            except Exception:
                logger.exception(
                    "Error looking up '%s' in source '%s'",
                    normalized_word,
                    source.source_name,
                )
                continue

            if entry is not None:
                entry.source = source.source_name
                # Populate cache if result came from a non-cache source
                if (
                    self._cache_source is not None
                    and source.source_name != self._cache_source.source_name
                ):
                    self._populate_cache(entry, language)
                return entry

        return None

    def _populate_cache(self, entry: DictEntry, language: str) -> None:
        """Store a lookup result in the cache source.

        Args:
            entry: The DictEntry to cache.
            language: Language code for the cache key.
        """
        if self._cache_source is None:
            return
        try:
            # The cache source is expected to implement a `store` method
            if hasattr(self._cache_source, "store"):
                self._cache_source.store(entry, language)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Failed to cache entry for word '%s'", entry.word)
