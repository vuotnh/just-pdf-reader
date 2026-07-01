"""Vocabulary service implementing the IVocabularyService protocol.

Orchestrates vocabulary management including word saving, editing, deletion
with cascade, mastery level tracking, and export (CSV/Anki).

Requirements: 7.1–7.7
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from src.domain.enums import CardType, MasteryLevel, SRAlgorithm
from src.domain.models import ReviewCard, VocabularyEntry
from src.domain.value_objects import TextPosition, VocabFilter
from src.infrastructure.dictionary.lookup_chain import DictEntry
from src.infrastructure.repositories.vocabulary_repository import (
    ReviewCardRepository,
    VocabularyRepository,
)


class ExportFormat(Enum):
    """Supported vocabulary export formats."""

    CSV = "csv"
    ANKI = "anki"


@dataclass
class VocabUpdate:
    """Fields that can be updated on a vocabulary entry."""

    definition: str | None = None
    pronunciation: str | None = None
    part_of_speech: str | None = None
    example_sentence: str | None = None
    mastery_level: MasteryLevel | None = None


class VocabularyService:
    """Application-layer service for vocabulary management.

    Implements the IVocabularyService protocol from the design document,
    coordinating repositories to handle:
    - Saving words from dictionary lookup with all fields
    - Auto-assignment to default review queue (due_date = today)
    - Mastery level tracking (New, Learning, Reviewing, Mastered)
    - Vocabulary entry editing and deletion with cascade
    - Export to CSV and Anki-compatible format
    """

    def __init__(
        self,
        vocabulary_repo: VocabularyRepository,
        review_card_repo: ReviewCardRepository,
    ) -> None:
        self._vocabulary_repo = vocabulary_repo
        self._review_card_repo = review_card_repo

    # ------------------------------------------------------------------
    # Save word (Requirement 7.1, 7.2)
    # ------------------------------------------------------------------

    def save_word(
        self,
        word: str,
        entry: DictEntry,
        book_id: str | None = None,
        position: TextPosition | None = None,
    ) -> VocabularyEntry:
        """Save a looked-up word to the vocabulary list.

        Stores the word with its definition, pronunciation, example sentence,
        source book, and page/position reference. Automatically assigns the
        word to the default review queue with due_date = today.

        Args:
            word: The word to save.
            entry: The DictEntry from dictionary lookup.
            book_id: Optional source book ID.
            position: Optional text position where the word was found.

        Returns:
            The created VocabularyEntry domain object.
        """
        now = datetime.now(UTC)

        # Extract definition from DictEntry
        definition = self._extract_definition(entry)

        # Extract first example sentence
        example_sentence = entry.examples[0] if entry.examples else None

        # Extract part of speech
        part_of_speech = ""
        if entry.parts_of_speech:
            part_of_speech = entry.parts_of_speech[0].pos

        # Serialize position data
        position_data: str | None = None
        if position is not None:
            position_data = json.dumps({
                "page": position.page,
                "chapter": position.chapter,
                "start_offset": position.start_offset,
                "end_offset": position.end_offset,
            })

        # Create vocabulary entry
        vocab_entry = VocabularyEntry(
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

        # Persist the vocabulary entry
        saved_entry = self._vocabulary_repo.add(vocab_entry)

        # Auto-assign to default review queue with due_date = today
        self._create_default_review_card(saved_entry.id, now)

        return saved_entry

    # ------------------------------------------------------------------
    # Query operations (Requirement 7.3)
    # ------------------------------------------------------------------

    def get_vocabulary(self, filter: VocabFilter | None = None) -> list[VocabularyEntry]:
        """Get all vocabulary entries, sorted by date added.

        Supports filtering by book, tag, or mastery level.

        Args:
            filter: Optional filter criteria.

        Returns:
            List of VocabularyEntry domain objects.
        """
        return self._vocabulary_repo.get_all(filter=filter)

    def get_entry(self, entry_id: str) -> VocabularyEntry | None:
        """Get a single vocabulary entry by ID.

        Args:
            entry_id: The entry's unique ID.

        Returns:
            The VocabularyEntry domain object, or None if not found.
        """
        return self._vocabulary_repo.get_by_id(entry_id)

    # ------------------------------------------------------------------
    # Update operations (Requirement 7.4, 7.5)
    # ------------------------------------------------------------------

    def update_entry(self, entry_id: str, updates: VocabUpdate) -> VocabularyEntry:
        """Update a vocabulary entry's fields.

        Persists changes to definition, example, pronunciation, part of speech,
        or mastery level.

        Args:
            entry_id: The ID of the entry to update.
            updates: The fields to update.

        Returns:
            The updated VocabularyEntry domain object.

        Raises:
            ValueError: If the entry does not exist.
        """
        existing = self._vocabulary_repo.get_by_id(entry_id)
        if existing is None:
            raise ValueError(f"VocabularyEntry '{entry_id}' not found.")

        # Apply updates
        if updates.definition is not None:
            existing.definition = updates.definition
        if updates.pronunciation is not None:
            existing.pronunciation = updates.pronunciation
        if updates.part_of_speech is not None:
            existing.part_of_speech = updates.part_of_speech
        if updates.example_sentence is not None:
            existing.example_sentence = updates.example_sentence
        if updates.mastery_level is not None:
            existing.mastery_level = updates.mastery_level

        existing.updated_at = datetime.now(UTC)

        return self._vocabulary_repo.update(existing)

    def update_mastery_level(self, entry_id: str, level: MasteryLevel) -> None:
        """Update the mastery level of a vocabulary entry.

        Args:
            entry_id: The ID of the entry.
            level: The new mastery level.

        Raises:
            ValueError: If the entry does not exist.
        """
        success = self._vocabulary_repo.update_mastery_level(entry_id, level)
        if not success:
            raise ValueError(f"VocabularyEntry '{entry_id}' not found.")

    # ------------------------------------------------------------------
    # Delete operations (Requirement 7.6)
    # ------------------------------------------------------------------

    def delete_entry(self, entry_id: str) -> None:
        """Delete a vocabulary entry with cascade to review cards and logs.

        Removes the word from the vocabulary list and all associated
        review schedules (cards and logs).

        Args:
            entry_id: The ID of the entry to delete.

        Raises:
            ValueError: If the entry does not exist.
        """
        success = self._vocabulary_repo.delete(entry_id)
        if not success:
            raise ValueError(f"VocabularyEntry '{entry_id}' not found.")

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def add_tag(self, entry_id: str, tag: str) -> None:
        """Associate a tag with a vocabulary entry.

        Args:
            entry_id: The ID of the vocabulary entry.
            tag: The tag name to associate.

        Raises:
            ValueError: If the entry does not exist.
        """
        success = self._vocabulary_repo.add_tag(entry_id, tag)
        if not success:
            raise ValueError(f"VocabularyEntry '{entry_id}' not found.")

    def remove_tag(self, entry_id: str, tag: str) -> None:
        """Remove a tag from a vocabulary entry.

        Args:
            entry_id: The ID of the vocabulary entry.
            tag: The tag name to remove.

        Raises:
            ValueError: If the entry or tag association not found.
        """
        success = self._vocabulary_repo.remove_tag(entry_id, tag)
        if not success:
            raise ValueError(
                f"Failed to remove tag '{tag}' from entry '{entry_id}'."
            )

    # ------------------------------------------------------------------
    # Export operations (Requirement 7.7)
    # ------------------------------------------------------------------

    def export(self, format: ExportFormat) -> bytes:
        """Export all vocabulary entries to the specified format.

        Supports CSV and Anki-compatible (tab-separated) formats.

        Args:
            format: The export format (CSV or ANKI).

        Returns:
            The exported data as bytes.
        """
        entries = self._vocabulary_repo.get_all()

        if format == ExportFormat.CSV:
            return self._export_csv(entries)
        elif format == ExportFormat.ANKI:
            return self._export_anki(entries)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_definition(self, entry: DictEntry) -> str:
        """Extract a combined definition string from a DictEntry."""
        all_definitions: list[str] = []
        for pos in entry.parts_of_speech:
            pos_label = f"({pos.pos}) " if pos.pos else ""
            for defn in pos.definitions:
                all_definitions.append(f"{pos_label}{defn}")

        if all_definitions:
            return "; ".join(all_definitions)
        return ""

    def _create_default_review_card(self, vocabulary_id: str, now: datetime) -> None:
        """Create a default flashcard review card with due_date = today.

        Args:
            vocabulary_id: The ID of the vocabulary entry.
            now: The current datetime for due_date and timestamps.
        """
        card = ReviewCard(
            id=str(uuid.uuid4()),
            vocabulary_id=vocabulary_id,
            card_type=CardType.FLASHCARD,
            difficulty=5.0,
            stability=0.4,
            ease_factor=2.5,
            repetitions=0,
            last_interval=0.0,
            due_date=now,
            algorithm=SRAlgorithm.FSRS,
            created_at=now,
            updated_at=now,
        )
        self._review_card_repo.add(card)

    def _export_csv(self, entries: list[VocabularyEntry]) -> bytes:
        """Export vocabulary entries to CSV format.

        Columns: word, definition, pronunciation, part_of_speech,
                 example_sentence, mastery_level, source_book, created_at
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "word",
            "definition",
            "pronunciation",
            "part_of_speech",
            "example_sentence",
            "mastery_level",
            "book_id",
            "created_at",
        ])

        # Data rows
        for entry in entries:
            writer.writerow([
                entry.word,
                entry.definition,
                entry.pronunciation or "",
                entry.part_of_speech or "",
                entry.example_sentence or "",
                entry.mastery_level.value,
                entry.book_id or "",
                entry.created_at.isoformat(),
            ])

        return output.getvalue().encode("utf-8")

    def _export_anki(self, entries: list[VocabularyEntry]) -> bytes:
        """Export vocabulary entries to Anki-compatible format.

        Anki uses tab-separated values with front and back fields.
        Front: word (with pronunciation)
        Back: definition + example sentence

        The file includes the Anki header comment for import compatibility.
        """
        lines: list[str] = []

        # Anki import header
        lines.append("#separator:tab")
        lines.append("#html:false")
        lines.append("#columns:front\tback\ttags")

        for entry in entries:
            # Front: word with pronunciation
            front = entry.word
            if entry.pronunciation:
                front = f"{entry.word} [{entry.pronunciation}]"

            # Back: definition + example
            back_parts: list[str] = []
            if entry.definition:
                back_parts.append(entry.definition)
            if entry.example_sentence:
                back_parts.append(f"Example: {entry.example_sentence}")
            back = " | ".join(back_parts) if back_parts else ""

            # Tags: mastery level
            tags = entry.mastery_level.value

            lines.append(f"{front}\t{back}\t{tags}")

        return "\n".join(lines).encode("utf-8")
