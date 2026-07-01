"""Dictionary service implementing the IDictionaryService protocol.

Orchestrates word lookup through the dictionary lookup chain,
provides available sources listing, and vocabulary saving.

Requirements: 6.1–6.8, 12.2
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from src.domain.models import VocabularyEntry
from src.domain.enums import MasteryLevel
from src.domain.value_objects import TextPosition
from src.infrastructure.dictionary.lookup_chain import DictionaryLookupChain, DictEntry

logger = logging.getLogger(__name__)


class DictionaryService:
    """Application-layer service for dictionary lookups.

    Implements the IDictionaryService protocol from the design document,
    coordinating the lookup chain infrastructure to handle:
    - Word lookup through the chain (cache → StarDict → online API)
    - Listing available dictionary sources
    - Saving looked-up words to vocabulary
    """

    def __init__(
        self,
        lookup_chain: DictionaryLookupChain,
    ) -> None:
        """Initialize the dictionary service.

        Args:
            lookup_chain: The configured lookup chain with sources in priority order.
        """
        self._lookup_chain = lookup_chain

    # ------------------------------------------------------------------
    # Lookup operations
    # ------------------------------------------------------------------

    def lookup(self, word: str, source: str | None = None, language: str = "en") -> DictEntry | None:
        """Look up a word definition.

        If a specific source is specified, only that source is queried.
        Otherwise, the full chain is traversed in priority order.

        Args:
            word: The word to look up.
            source: Optional source name to restrict lookup to (e.g. "oxford", "stardict").
            language: Language code for lookup context.

        Returns:
            DictEntry if found, None otherwise.
        """
        if not word or not word.strip():
            return None

        if source is not None:
            return self._lookup_from_source(word, source, language)

        return self._lookup_chain.lookup(word, language)

    def get_available_sources(self) -> list[str]:
        """Get the list of available dictionary source names.

        Returns:
            List of source name strings (e.g. ["cache", "stardict", "oxford"]).
        """
        return [s.source_name for s in self._lookup_chain.sources]

    # ------------------------------------------------------------------
    # Vocabulary saving
    # ------------------------------------------------------------------

    def create_vocabulary_entry(
        self,
        word: str,
        entry: DictEntry,
        book_id: str | None = None,
        position: TextPosition | None = None,
    ) -> VocabularyEntry:
        """Create a VocabularyEntry domain object from a dictionary lookup result.

        Extracts definition, pronunciation, part of speech, and example
        sentence from the DictEntry to populate the vocabulary entry.
        The entry is assigned mastery level NEW for spaced repetition.

        Args:
            word: The word to save.
            entry: The DictEntry from the dictionary lookup.
            book_id: Optional source book ID.
            position: Optional text position where the word was found.

        Returns:
            A VocabularyEntry domain object ready for persistence.
        """
        # Extract first definition
        definition = ""
        part_of_speech = ""
        if entry.parts_of_speech:
            first_pos = entry.parts_of_speech[0]
            part_of_speech = first_pos.pos
            if first_pos.definitions:
                definition = first_pos.definitions[0]

        # Combine all definitions for a richer entry
        all_definitions: list[str] = []
        for pos in entry.parts_of_speech:
            pos_label = f"({pos.pos}) " if pos.pos else ""
            for defn in pos.definitions:
                all_definitions.append(f"{pos_label}{defn}")
        if all_definitions:
            definition = "; ".join(all_definitions)

        # Extract first example sentence
        example_sentence = entry.examples[0] if entry.examples else None

        # Serialize position data
        position_data: str | None = None
        if position is not None:
            position_data = json.dumps({
                "page": position.page,
                "chapter": position.chapter,
                "start_offset": position.start_offset,
                "end_offset": position.end_offset,
            })

        now = datetime.now(UTC)

        return VocabularyEntry(
            id=str(uuid.uuid4()),
            word=word,
            definition=definition,
            pronunciation=entry.ipa or None,
            part_of_speech=part_of_speech or None,
            example_sentence=example_sentence,
            book_id=book_id,
            position_data=position_data,
            mastery_level=MasteryLevel.NEW,
            created_at=now,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _lookup_from_source(
        self, word: str, source_name: str, language: str
    ) -> DictEntry | None:
        """Look up a word from a specific source only.

        Args:
            word: The word to look up.
            source_name: The source name to query.
            language: Language code.

        Returns:
            DictEntry if found in the specified source, None otherwise.
        """
        normalized_word = word.strip().lower()
        if not normalized_word:
            return None

        for source in self._lookup_chain.sources:
            if source.source_name == source_name:
                try:
                    entry = source.lookup(normalized_word, language)
                    if entry is not None:
                        entry.source = source.source_name
                    return entry
                except Exception:
                    logger.exception(
                        "Error looking up '%s' in source '%s'",
                        normalized_word,
                        source_name,
                    )
                    return None

        logger.warning("Dictionary source '%s' not found in chain", source_name)
        return None
