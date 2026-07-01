"""Vocabulary QML controller bridging VocabularyService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for vocabulary management including:
- Vocabulary list model with word entries sorted by date
- Filtering by book, tag, or mastery level
- Editing and deleting vocabulary entries
- Export to CSV or Anki-compatible format

Requirements: 7.3–7.7, 14.3
"""

from __future__ import annotations

import json
import logging
from enum import IntEnum

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.vocabulary_service import ExportFormat, VocabUpdate, VocabularyService
from src.domain.enums import MasteryLevel
from src.domain.models import VocabularyEntry
from src.domain.value_objects import VocabFilter

logger = logging.getLogger(__name__)


class VocabRoles(IntEnum):
    """Custom roles for VocabularyListModel data access from QML."""

    IdRole = Qt.ItemDataRole.UserRole + 1
    WordRole = Qt.ItemDataRole.UserRole + 2
    DefinitionRole = Qt.ItemDataRole.UserRole + 3
    PronunciationRole = Qt.ItemDataRole.UserRole + 4
    PartOfSpeechRole = Qt.ItemDataRole.UserRole + 5
    ExampleSentenceRole = Qt.ItemDataRole.UserRole + 6
    MasteryLevelRole = Qt.ItemDataRole.UserRole + 7
    BookIdRole = Qt.ItemDataRole.UserRole + 8
    CreatedAtRole = Qt.ItemDataRole.UserRole + 9
    UpdatedAtRole = Qt.ItemDataRole.UserRole + 10


class VocabularyListModel(QAbstractListModel):
    """QAbstractListModel exposing vocabulary entries to QML.

    Provides role-based data access for the vocabulary word list,
    sorted by date added (most recent first).
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[VocabularyEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return the number of vocabulary entries in the model."""
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self._entries):
            return None

        entry = self._entries[index.row()]

        if role == VocabRoles.IdRole:
            return entry.id
        elif role == VocabRoles.WordRole:
            return entry.word
        elif role == VocabRoles.DefinitionRole:
            return entry.definition
        elif role == VocabRoles.PronunciationRole:
            return entry.pronunciation or ""
        elif role == VocabRoles.PartOfSpeechRole:
            return entry.part_of_speech or ""
        elif role == VocabRoles.ExampleSentenceRole:
            return entry.example_sentence or ""
        elif role == VocabRoles.MasteryLevelRole:
            return entry.mastery_level.value
        elif role == VocabRoles.BookIdRole:
            return entry.book_id or ""
        elif role == VocabRoles.CreatedAtRole:
            return entry.created_at.isoformat()
        elif role == VocabRoles.UpdatedAtRole:
            return entry.updated_at.isoformat()
        elif role == Qt.ItemDataRole.DisplayRole:
            return entry.word

        return None

    def roleNames(self) -> dict[int, bytes]:
        """Map role enum values to QML-accessible role name strings."""
        return {
            VocabRoles.IdRole: b"entryId",
            VocabRoles.WordRole: b"word",
            VocabRoles.DefinitionRole: b"definition",
            VocabRoles.PronunciationRole: b"pronunciation",
            VocabRoles.PartOfSpeechRole: b"partOfSpeech",
            VocabRoles.ExampleSentenceRole: b"exampleSentence",
            VocabRoles.MasteryLevelRole: b"masteryLevel",
            VocabRoles.BookIdRole: b"bookId",
            VocabRoles.CreatedAtRole: b"createdAt",
            VocabRoles.UpdatedAtRole: b"updatedAt",
        }

    def set_entries(self, entries: list[VocabularyEntry]) -> None:
        """Replace the entire entry list and notify views of the change."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def get_entries(self) -> list[VocabularyEntry]:
        """Return the current list of vocabulary entries."""
        return list(self._entries)


class VocabularyController(QObject):
    """QObject controller bridging VocabularyService to QML.

    Exposes vocabulary management operations as slots callable from QML
    and emits signals to notify the UI of state changes. Provides a list
    model for displaying vocabulary entries with filtering support.

    Requirements: 7.3–7.7, 14.3
    """

    # Signals
    vocabularyChanged = Signal()
    entryUpdated = Signal(str)  # entry ID
    entryDeleted = Signal(str)  # entry ID
    exportReady = Signal(str, str)  # format, file content (base64 or path)
    errorOccurred = Signal(str)  # error message
    filterChanged = Signal()

    def __init__(
        self,
        vocabulary_service: VocabularyService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = vocabulary_service
        self._vocab_model = VocabularyListModel(self)
        self._filter_book_id: str = ""
        self._filter_tag: str = ""
        self._filter_mastery: str = ""

        # Load initial vocabulary
        self._refresh_vocabulary()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(QObject, constant=True)
    def vocabularyModel(self) -> VocabularyListModel:  # noqa: N802
        """The vocabulary list model for QML view binding."""
        return self._vocab_model

    @Property(int, notify=vocabularyChanged)
    def entryCount(self) -> int:  # noqa: N802
        """Number of vocabulary entries currently displayed."""
        return self._vocab_model.rowCount()

    @Property(str, notify=filterChanged)
    def filterBookId(self) -> str:  # noqa: N802
        """Current book filter value."""
        return self._filter_book_id

    @Property(str, notify=filterChanged)
    def filterTag(self) -> str:  # noqa: N802
        """Current tag filter value."""
        return self._filter_tag

    @Property(str, notify=filterChanged)
    def filterMastery(self) -> str:  # noqa: N802
        """Current mastery level filter value."""
        return self._filter_mastery

    # ------------------------------------------------------------------
    # Slots - Filtering
    # ------------------------------------------------------------------

    @Slot(str)
    def setFilterBookId(self, book_id: str) -> None:  # noqa: N802
        """Set the book filter for vocabulary list.

        Args:
            book_id: Book ID to filter by, or empty string to clear.
        """
        self._filter_book_id = book_id
        self.filterChanged.emit()
        self._refresh_vocabulary()

    @Slot(str)
    def setFilterTag(self, tag: str) -> None:  # noqa: N802
        """Set the tag filter for vocabulary list.

        Args:
            tag: Tag name to filter by, or empty string to clear.
        """
        self._filter_tag = tag
        self.filterChanged.emit()
        self._refresh_vocabulary()

    @Slot(str)
    def setFilterMastery(self, mastery_level: str) -> None:  # noqa: N802
        """Set the mastery level filter for vocabulary list.

        Args:
            mastery_level: Mastery level value (new, learning, reviewing, mastered),
                          or empty string to clear.
        """
        self._filter_mastery = mastery_level
        self.filterChanged.emit()
        self._refresh_vocabulary()

    @Slot()
    def clearFilters(self) -> None:  # noqa: N802
        """Clear all active filters and show all vocabulary entries."""
        self._filter_book_id = ""
        self._filter_tag = ""
        self._filter_mastery = ""
        self.filterChanged.emit()
        self._refresh_vocabulary()

    # ------------------------------------------------------------------
    # Slots - Edit
    # ------------------------------------------------------------------

    @Slot(str, str, str, str, str)
    def updateEntry(  # noqa: N802
        self,
        entry_id: str,
        definition: str,
        pronunciation: str,
        example_sentence: str,
        mastery_level: str,
    ) -> None:
        """Update a vocabulary entry's fields.

        Args:
            entry_id: The ID of the entry to update.
            definition: New definition (empty string means no change).
            pronunciation: New pronunciation (empty string means no change).
            example_sentence: New example sentence (empty string means no change).
            mastery_level: New mastery level value (empty string means no change).
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        updates = VocabUpdate()
        if definition:
            updates.definition = definition
        if pronunciation:
            updates.pronunciation = pronunciation
        if example_sentence:
            updates.example_sentence = example_sentence
        if mastery_level:
            try:
                updates.mastery_level = MasteryLevel(mastery_level)
            except ValueError:
                self.errorOccurred.emit(f"Invalid mastery level: {mastery_level}")
                return

        try:
            self._service.update_entry(entry_id, updates)
            self.entryUpdated.emit(entry_id)
            self._refresh_vocabulary()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str, str)
    def updateMasteryLevel(self, entry_id: str, mastery_level: str) -> None:  # noqa: N802
        """Update the mastery level of a vocabulary entry.

        Args:
            entry_id: The ID of the entry to update.
            mastery_level: New mastery level value (new, learning, reviewing, mastered).
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        try:
            level = MasteryLevel(mastery_level)
            self._service.update_mastery_level(entry_id, level)
            self.entryUpdated.emit(entry_id)
            self._refresh_vocabulary()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    # ------------------------------------------------------------------
    # Slots - Delete
    # ------------------------------------------------------------------

    @Slot(str)
    def deleteEntry(self, entry_id: str) -> None:  # noqa: N802
        """Delete a vocabulary entry and its associated review schedules.

        Args:
            entry_id: The ID of the entry to delete.
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        try:
            self._service.delete_entry(entry_id)
            self.entryDeleted.emit(entry_id)
            self._refresh_vocabulary()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    # ------------------------------------------------------------------
    # Slots - Tag Management
    # ------------------------------------------------------------------

    @Slot(str, str)
    def addTag(self, entry_id: str, tag: str) -> None:  # noqa: N802
        """Add a tag to a vocabulary entry.

        Args:
            entry_id: The ID of the vocabulary entry.
            tag: The tag name to add.
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        try:
            self._service.add_tag(entry_id, tag)
            self.vocabularyChanged.emit()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str, str)
    def removeTag(self, entry_id: str, tag: str) -> None:  # noqa: N802
        """Remove a tag from a vocabulary entry.

        Args:
            entry_id: The ID of the vocabulary entry.
            tag: The tag name to remove.
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        try:
            self._service.remove_tag(entry_id, tag)
            self.vocabularyChanged.emit()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    # ------------------------------------------------------------------
    # Slots - Export
    # ------------------------------------------------------------------

    @Slot(str)
    def exportVocabulary(self, format_str: str) -> None:  # noqa: N802
        """Export all vocabulary entries in the specified format.

        Args:
            format_str: Export format ("csv" or "anki").
        """
        if self._service is None:
            self.errorOccurred.emit("Vocabulary service not available")
            return

        try:
            export_format = ExportFormat(format_str)
        except ValueError:
            self.errorOccurred.emit(f"Unsupported export format: {format_str}")
            return

        try:
            data = self._service.export(export_format)
            content = data.decode("utf-8")
            self.exportReady.emit(format_str, content)
        except Exception as e:
            logger.exception("Failed to export vocabulary as %s", format_str)
            self.errorOccurred.emit(f"Export failed: {e}")

    # ------------------------------------------------------------------
    # Slots - Query
    # ------------------------------------------------------------------

    @Slot(str, result=str)
    def getEntryJson(self, entry_id: str) -> str:  # noqa: N802
        """Get a vocabulary entry's full data as JSON.

        Args:
            entry_id: The entry ID to retrieve.

        Returns:
            JSON string with entry data, or empty string if not found.
        """
        if self._service is None:
            return ""

        entry = self._service.get_entry(entry_id)
        if entry is None:
            return ""

        return json.dumps({
            "id": entry.id,
            "word": entry.word,
            "definition": entry.definition,
            "pronunciation": entry.pronunciation or "",
            "partOfSpeech": entry.part_of_speech or "",
            "exampleSentence": entry.example_sentence or "",
            "masteryLevel": entry.mastery_level.value,
            "bookId": entry.book_id or "",
            "createdAt": entry.created_at.isoformat(),
            "updatedAt": entry.updated_at.isoformat(),
        }, ensure_ascii=False)

    @Slot()
    def refresh(self) -> None:
        """Manually refresh the vocabulary list from the service."""
        self._refresh_vocabulary()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_vocabulary(self) -> None:
        """Reload vocabulary entries from the service with current filters."""
        if self._service is None:
            self._vocab_model.set_entries([])
            self.vocabularyChanged.emit()
            return

        # Build filter from current state
        vocab_filter: VocabFilter | None = None
        book_id = self._filter_book_id or None
        tag = self._filter_tag or None
        mastery: MasteryLevel | None = None

        if self._filter_mastery:
            try:
                mastery = MasteryLevel(self._filter_mastery)
            except ValueError:
                mastery = None

        if book_id or tag or mastery:
            vocab_filter = VocabFilter(
                book_id=book_id,
                tag=tag,
                mastery_level=mastery,
            )

        entries = self._service.get_vocabulary(filter=vocab_filter)
        self._vocab_model.set_entries(entries)
        self.vocabularyChanged.emit()
