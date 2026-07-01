"""Dictionary QML controller bridging DictionaryService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for dictionary lookups, popup display, source selection, and vocabulary saving.
Designed to respond to double-click word lookup within the 100ms target.

Requirements: 6.1–6.8, 12.2
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import (
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.dictionary_service import DictionaryService
from src.domain.models import VocabularyEntry
from src.domain.value_objects import TextPosition
from src.infrastructure.dictionary.lookup_chain import DictEntry

logger = logging.getLogger(__name__)


class DictionaryController(QObject):
    """QObject controller for dictionary lookups and popup management.

    Bridges the DictionaryService to the QML DictionaryPopup, providing
    slots for word lookup (triggered by double-click), source switching,
    and vocabulary saving. Exposes lookup results as properties for
    QML data binding.

    Requirements: 6.1–6.8, 12.2
    """

    # Signals
    lookupStarted = Signal()
    lookupComplete = Signal()
    lookupFailed = Signal(str)  # error/not-found message
    popupVisibleChanged = Signal(bool)
    wordChanged = Signal()
    pronunciationChanged = Signal()
    definitionsChanged = Signal()
    examplesChanged = Signal()
    synonymsChanged = Signal()
    sourceChanged = Signal()
    availableSourcesChanged = Signal()
    vocabularySaved = Signal(str)  # word that was saved
    errorOccurred = Signal(str)  # error message

    def __init__(
        self,
        dictionary_service: DictionaryService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = dictionary_service
        self._current_word: str = ""
        self._current_entry: DictEntry | None = None
        self._popup_visible: bool = False
        self._current_source: str = ""
        self._available_sources: list[str] = []

        # Context for vocabulary saving
        self._lookup_book_id: str = ""
        self._lookup_page: int = -1
        self._lookup_chapter: str = ""
        self._lookup_start_offset: int = 0
        self._lookup_end_offset: int = 0

        # Load available sources
        if self._service:
            self._available_sources = self._service.get_available_sources()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(bool, notify=popupVisibleChanged)
    def popupVisible(self) -> bool:  # noqa: N802
        """Whether the dictionary popup is currently visible."""
        return self._popup_visible

    @Property(str, notify=wordChanged)
    def word(self) -> str:
        """The currently looked-up word."""
        return self._current_word

    @Property(str, notify=pronunciationChanged)
    def pronunciation(self) -> str:
        """IPA pronunciation of the current word."""
        if self._current_entry:
            return self._current_entry.ipa
        return ""

    @Property(str, notify=definitionsChanged)
    def definitionsJson(self) -> str:  # noqa: N802
        """JSON array of definitions grouped by part of speech.

        Format: [{"pos": "noun", "definitions": ["def1", "def2"]}, ...]
        """
        if self._current_entry and self._current_entry.parts_of_speech:
            data = [
                {"pos": p.pos, "definitions": p.definitions}
                for p in self._current_entry.parts_of_speech
            ]
            return json.dumps(data, ensure_ascii=False)
        return "[]"

    @Property(str, notify=examplesChanged)
    def examplesJson(self) -> str:  # noqa: N802
        """JSON array of example sentences."""
        if self._current_entry and self._current_entry.examples:
            return json.dumps(self._current_entry.examples, ensure_ascii=False)
        return "[]"

    @Property(str, notify=synonymsChanged)
    def synonymsJson(self) -> str:  # noqa: N802
        """JSON array of synonyms."""
        if self._current_entry and self._current_entry.synonyms:
            return json.dumps(self._current_entry.synonyms, ensure_ascii=False)
        return "[]"

    @Property(str, notify=sourceChanged)
    def currentSource(self) -> str:  # noqa: N802
        """The source that provided the current definition."""
        return self._current_source

    @Property(str, notify=availableSourcesChanged)
    def availableSourcesJson(self) -> str:  # noqa: N802
        """JSON array of available dictionary source names."""
        return json.dumps(self._available_sources)

    # ------------------------------------------------------------------
    # Slots - Lookup
    # ------------------------------------------------------------------

    @Slot(str)
    def lookupWord(self, word: str) -> None:  # noqa: N802
        """Look up a word through the dictionary chain.

        Designed to be called on double-click events. The lookup chain
        starts with cache for sub-100ms response when cached.

        Args:
            word: The word to look up.
        """
        if not word or not word.strip():
            return

        self._current_word = word.strip()
        self.wordChanged.emit()
        self.lookupStarted.emit()

        if self._service is None:
            self.lookupFailed.emit("Dictionary service not available")
            return

        entry = self._service.lookup(self._current_word)
        self._handle_lookup_result(entry)

    @Slot(str, int, str, int, int)
    def lookupWordWithContext(  # noqa: N802
        self,
        word: str,
        page: int,
        chapter: str,
        start_offset: int,
        end_offset: int,
    ) -> None:
        """Look up a word with reading context for vocabulary saving.

        Stores the position context so that if the user saves the word
        to vocabulary, the source location is preserved.

        Args:
            word: The word to look up.
            page: Page number (-1 if not applicable).
            chapter: Chapter identifier (empty if not applicable).
            start_offset: Start character offset of the word.
            end_offset: End character offset of the word.
        """
        self._lookup_page = page
        self._lookup_chapter = chapter
        self._lookup_start_offset = start_offset
        self._lookup_end_offset = end_offset
        self.lookupWord(word)

    @Slot(str)
    def setBookContext(self, book_id: str) -> None:  # noqa: N802
        """Set the current book context for vocabulary saving.

        Args:
            book_id: The ID of the book being read.
        """
        self._lookup_book_id = book_id

    @Slot(str)
    def lookupFromSource(self, source_name: str) -> None:  # noqa: N802
        """Re-look up the current word from a specific dictionary source.

        Used when the user selects a different source in the popup.

        Args:
            source_name: The source to query (e.g. "oxford", "stardict").
        """
        if not self._current_word:
            return

        if self._service is None:
            self.lookupFailed.emit("Dictionary service not available")
            return

        self.lookupStarted.emit()
        entry = self._service.lookup(self._current_word, source=source_name)
        self._handle_lookup_result(entry)

    # ------------------------------------------------------------------
    # Slots - Popup Management
    # ------------------------------------------------------------------

    @Slot()
    def showPopup(self) -> None:  # noqa: N802
        """Show the dictionary popup."""
        self._popup_visible = True
        self.popupVisibleChanged.emit(True)

    @Slot()
    def hidePopup(self) -> None:  # noqa: N802
        """Hide the dictionary popup."""
        self._popup_visible = False
        self.popupVisibleChanged.emit(False)
        # Clear state
        self._current_word = ""
        self._current_entry = None
        self._current_source = ""
        self.wordChanged.emit()

    # ------------------------------------------------------------------
    # Slots - Vocabulary Saving
    # ------------------------------------------------------------------

    @Slot(result=str)
    def saveToVocabulary(self) -> str:  # noqa: N802
        """Save the current looked-up word to vocabulary.

        Creates a VocabularyEntry from the current DictEntry with
        position context from the reading session. The entry is
        assigned to the default review queue with due_date = today.

        Returns:
            JSON string with the saved vocabulary entry data, or
            empty string on failure.
        """
        if self._service is None:
            self.errorOccurred.emit("Dictionary service not available")
            return ""

        if self._current_entry is None:
            self.errorOccurred.emit("No word definition to save")
            return ""

        # Build position from saved context
        position: TextPosition | None = None
        if self._lookup_page >= 0 or self._lookup_chapter:
            position = TextPosition(
                page=self._lookup_page if self._lookup_page >= 0 else None,
                chapter=self._lookup_chapter or None,
                start_offset=self._lookup_start_offset,
                end_offset=self._lookup_end_offset,
            )

        try:
            vocab_entry = self._service.create_vocabulary_entry(
                word=self._current_word,
                entry=self._current_entry,
                book_id=self._lookup_book_id or None,
                position=position,
            )

            self.vocabularySaved.emit(self._current_word)

            # Return entry data as JSON for QML confirmation
            return json.dumps({
                "id": vocab_entry.id,
                "word": vocab_entry.word,
                "definition": vocab_entry.definition,
                "pronunciation": vocab_entry.pronunciation or "",
                "mastery_level": vocab_entry.mastery_level.value,
            }, ensure_ascii=False)

        except Exception as e:
            logger.exception("Failed to save word '%s' to vocabulary", self._current_word)
            self.errorOccurred.emit(f"Failed to save: {e}")
            return ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _handle_lookup_result(self, entry: DictEntry | None) -> None:
        """Process a lookup result and update properties/signals.

        Args:
            entry: The lookup result, or None if not found.
        """
        if entry is None:
            self._current_entry = None
            self._current_source = ""
            self.lookupFailed.emit(
                f"Definition not found for '{self._current_word}'"
            )
            # Still show popup with not-found message
            self._popup_visible = True
            self.popupVisibleChanged.emit(True)
            self.definitionsChanged.emit()
            self.examplesChanged.emit()
            self.synonymsChanged.emit()
            self.pronunciationChanged.emit()
            self.sourceChanged.emit()
            return

        self._current_entry = entry
        self._current_source = entry.source
        self._popup_visible = True

        # Emit all property change signals
        self.pronunciationChanged.emit()
        self.definitionsChanged.emit()
        self.examplesChanged.emit()
        self.synonymsChanged.emit()
        self.sourceChanged.emit()
        self.popupVisibleChanged.emit(True)
        self.lookupComplete.emit()
