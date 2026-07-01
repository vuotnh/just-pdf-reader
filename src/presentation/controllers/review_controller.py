"""Review Session QML controller bridging SpacedRepetitionService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for review session management including:
- Session start/end with deck filtering
- Card display (word, definition, cloze text, MCQ options)
- Rating buttons (Again, Hard, Good, Easy)
- Session progress tracking
- Daily stats and 7-day forecast
- Review mode switching (flashcard, MCQ, typing, cloze)

Requirements: 8.2–8.6, 14.1
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from PySide6.QtCore import (
    QObject,
    Property,
    Signal,
    Slot,
)

from src.application.services.spaced_repetition_service import (
    DailyStats,
    ReviewSession,
    SessionStats,
    SpacedRepetitionService,
)
from src.domain.enums import CardType, Rating
from src.domain.value_objects import DeckFilter
from src.infrastructure.repositories.vocabulary_repository import VocabularyRepository

logger = logging.getLogger(__name__)


class ReviewController(QObject):
    """QObject controller bridging SpacedRepetitionService to QML.

    Exposes review session operations as slots callable from QML
    and emits signals to notify the UI of state changes. Provides
    card display data, rating, progress, stats, and mode switching.

    Requirements: 8.2–8.6, 14.1
    """

    # Signals
    sessionStarted = Signal()
    sessionEnded = Signal()
    cardChanged = Signal()
    progressChanged = Signal()
    statsChanged = Signal()
    modeChanged = Signal()
    errorOccurred = Signal(str)

    def __init__(
        self,
        spaced_repetition_service: SpacedRepetitionService | None = None,
        vocabulary_repo: VocabularyRepository | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = spaced_repetition_service
        self._vocabulary_repo = vocabulary_repo

        # Active session state
        self._session: ReviewSession | None = None
        self._session_id: str = ""

        # Current card display data
        self._current_word: str = ""
        self._current_definition: str = ""
        self._current_pronunciation: str = ""
        self._current_example: str = ""
        self._current_cloze_text: str = ""
        self._mcq_options: list[str] = []
        self._card_revealed: bool = False

        # Progress
        self._cards_reviewed: int = 0
        self._total_cards: int = 0

        # Review mode
        self._review_mode: str = CardType.FLASHCARD.value

        # Daily stats
        self._due_today: int = 0
        self._reviewed_today: int = 0
        self._new_cards: int = 0
        self._forecast: list[int] = [0] * 7

        # Load initial stats
        self._refresh_daily_stats()

    # ------------------------------------------------------------------
    # Properties - Session State
    # ------------------------------------------------------------------

    @Property(bool, notify=sessionStarted)
    def isSessionActive(self) -> bool:  # noqa: N802
        """Whether a review session is currently active."""
        return self._session is not None

    @Property(str, notify=cardChanged)
    def currentWord(self) -> str:  # noqa: N802
        """The word being reviewed on the current card."""
        return self._current_word

    @Property(str, notify=cardChanged)
    def currentDefinition(self) -> str:  # noqa: N802
        """The definition of the current card."""
        return self._current_definition

    @Property(str, notify=cardChanged)
    def currentPronunciation(self) -> str:  # noqa: N802
        """The pronunciation of the current word."""
        return self._current_pronunciation

    @Property(str, notify=cardChanged)
    def currentExample(self) -> str:  # noqa: N802
        """Example sentence for the current word."""
        return self._current_example

    @Property(str, notify=cardChanged)
    def currentClozeText(self) -> str:  # noqa: N802
        """Cloze deletion text for the current card."""
        return self._current_cloze_text

    @Property(str, notify=cardChanged)
    def mcqOptionsJson(self) -> str:  # noqa: N802
        """Multiple choice options as JSON array string."""
        return json.dumps(self._mcq_options, ensure_ascii=False)

    @Property(bool, notify=cardChanged)
    def cardRevealed(self) -> bool:  # noqa: N802
        """Whether the answer side of the card is revealed."""
        return self._card_revealed

    # ------------------------------------------------------------------
    # Properties - Progress
    # ------------------------------------------------------------------

    @Property(int, notify=progressChanged)
    def cardsReviewed(self) -> int:  # noqa: N802
        """Number of cards reviewed in the current session."""
        return self._cards_reviewed

    @Property(int, notify=progressChanged)
    def totalCards(self) -> int:  # noqa: N802
        """Total number of cards in the current session."""
        return self._total_cards

    @Property(float, notify=progressChanged)
    def progressPercent(self) -> float:  # noqa: N802
        """Session progress as a percentage (0.0 to 1.0)."""
        if self._total_cards == 0:
            return 0.0
        return self._cards_reviewed / self._total_cards

    # ------------------------------------------------------------------
    # Properties - Review Mode
    # ------------------------------------------------------------------

    @Property(str, notify=modeChanged)
    def reviewMode(self) -> str:  # noqa: N802
        """Current review mode (flashcard, mcq, typing, cloze)."""
        return self._review_mode

    # ------------------------------------------------------------------
    # Properties - Daily Stats
    # ------------------------------------------------------------------

    @Property(int, notify=statsChanged)
    def dueToday(self) -> int:  # noqa: N802
        """Number of cards due for review today."""
        return self._due_today

    @Property(int, notify=statsChanged)
    def reviewedToday(self) -> int:  # noqa: N802
        """Number of cards reviewed today."""
        return self._reviewed_today

    @Property(int, notify=statsChanged)
    def newCards(self) -> int:  # noqa: N802
        """Number of new cards available."""
        return self._new_cards

    @Property(str, notify=statsChanged)
    def forecastJson(self) -> str:  # noqa: N802
        """7-day forecast as a JSON array of integers."""
        return json.dumps(self._forecast)

    # ------------------------------------------------------------------
    # Slots - Session Management (Requirement 8.2)
    # ------------------------------------------------------------------

    @Slot()
    @Slot(str)
    def startSession(self, mode: str = "flashcard") -> None:  # noqa: N802
        """Start a new review session.

        Args:
            mode: Review mode to use (flashcard, mcq, typing, cloze).
        """
        if self._service is None:
            self.errorOccurred.emit("Spaced repetition service not available")
            return

        try:
            card_type = CardType(mode)
        except ValueError:
            card_type = CardType.FLASHCARD

        try:
            self._session = self._service.start_session(review_mode=card_type)
            self._session_id = self._session.id
            self._review_mode = card_type.value
            self._cards_reviewed = 0
            self._total_cards = self._session.total_cards
            self._card_revealed = False

            self.modeChanged.emit()
            self.progressChanged.emit()
            self.sessionStarted.emit()

            # Load the first card
            self._load_current_card()
        except Exception as e:
            logger.exception("Failed to start review session")
            self.errorOccurred.emit(f"Failed to start session: {e}")

    @Slot(str, str)
    def startFilteredSession(self, mode: str, filter_json: str) -> None:  # noqa: N802
        """Start a review session with deck filtering.

        Args:
            mode: Review mode (flashcard, mcq, typing, cloze).
            filter_json: JSON string with filter criteria
                         (book_id, tag, mastery_level, card_types).
        """
        if self._service is None:
            self.errorOccurred.emit("Spaced repetition service not available")
            return

        try:
            card_type = CardType(mode)
        except ValueError:
            card_type = CardType.FLASHCARD

        # Parse deck filter from JSON
        deck_filter: DeckFilter | None = None
        if filter_json:
            try:
                filter_data = json.loads(filter_json)
                deck_filter = DeckFilter(
                    book_id=filter_data.get("book_id"),
                    tag=filter_data.get("tag"),
                    mastery_level=filter_data.get("mastery_level"),
                    card_types=filter_data.get("card_types", []),
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Invalid filter JSON: %s", e)

        try:
            self._session = self._service.start_session(
                deck_filter=deck_filter,
                review_mode=card_type,
            )
            self._session_id = self._session.id
            self._review_mode = card_type.value
            self._cards_reviewed = 0
            self._total_cards = self._session.total_cards
            self._card_revealed = False

            self.modeChanged.emit()
            self.progressChanged.emit()
            self.sessionStarted.emit()

            self._load_current_card()
        except Exception as e:
            logger.exception("Failed to start filtered review session")
            self.errorOccurred.emit(f"Failed to start session: {e}")

    @Slot()
    def endSession(self) -> None:  # noqa: N802
        """End the current review session and emit final stats."""
        if self._service is None or not self._session_id:
            return

        try:
            self._service.end_session(self._session_id)
        except ValueError:
            pass  # Session already ended

        self._session = None
        self._session_id = ""
        self._current_word = ""
        self._current_definition = ""
        self._current_pronunciation = ""
        self._current_example = ""
        self._current_cloze_text = ""
        self._mcq_options = []
        self._card_revealed = False

        self.cardChanged.emit()
        self.sessionEnded.emit()
        self._refresh_daily_stats()

    # ------------------------------------------------------------------
    # Slots - Card Interaction (Requirement 8.3)
    # ------------------------------------------------------------------

    @Slot()
    def revealCard(self) -> None:  # noqa: N802
        """Reveal the answer side of the current card."""
        self._card_revealed = True
        self.cardChanged.emit()

    @Slot(int)
    def rateCard(self, rating_value: int) -> None:  # noqa: N802
        """Rate the current card and advance to the next one.

        Args:
            rating_value: Rating value (1=Again, 2=Hard, 3=Good, 4=Easy).
        """
        if self._service is None or self._session is None:
            self.errorOccurred.emit("No active session")
            return

        try:
            rating = Rating(rating_value)
        except ValueError:
            self.errorOccurred.emit(f"Invalid rating: {rating_value}")
            return

        # Get current card
        current_card = self._service.get_next_card(self._session_id)
        if current_card is None:
            return

        try:
            self._service.rate_card(
                card_id=current_card.id,
                rating=rating,
                session_id=self._session_id,
            )

            self._cards_reviewed += 1
            self._card_revealed = False
            self.progressChanged.emit()

            # Load next card or signal session complete
            self._load_current_card()
        except Exception as e:
            logger.exception("Failed to rate card")
            self.errorOccurred.emit(f"Failed to rate card: {e}")

    @Slot(str, result=bool)
    def checkTypingAnswer(self, answer: str) -> bool:  # noqa: N802
        """Check if the typed answer matches the current word.

        Args:
            answer: The user's typed answer.

        Returns:
            True if the answer matches (case-insensitive).
        """
        return answer.strip().lower() == self._current_word.strip().lower()

    # ------------------------------------------------------------------
    # Slots - Mode Switching (Requirement 8.4)
    # ------------------------------------------------------------------

    @Slot(str)
    def setReviewMode(self, mode: str) -> None:  # noqa: N802
        """Switch the review mode for the active session.

        Args:
            mode: Review mode (flashcard, mcq, typing, cloze).
        """
        try:
            card_type = CardType(mode)
        except ValueError:
            self.errorOccurred.emit(f"Invalid review mode: {mode}")
            return

        self._review_mode = card_type.value

        if self._service is not None and self._session_id:
            try:
                self._service.set_review_mode(self._session_id, card_type)
            except ValueError:
                pass

        self.modeChanged.emit()
        # Reload current card display for the new mode
        if self._session is not None:
            self._load_current_card()

    # ------------------------------------------------------------------
    # Slots - Stats (Requirements 8.5, 8.6)
    # ------------------------------------------------------------------

    @Slot(result=str)
    def getSessionStatsJson(self) -> str:  # noqa: N802
        """Get current session statistics as a JSON string.

        Returns:
            JSON with cards_reviewed, accuracy_rate, time_spent_seconds.
        """
        if self._service is None or not self._session_id:
            return json.dumps({
                "cards_reviewed": 0,
                "accuracy_rate": 0.0,
                "time_spent_seconds": 0.0,
            })

        try:
            stats = self._service.get_session_stats(self._session_id)
            return json.dumps({
                "cards_reviewed": stats.cards_reviewed,
                "accuracy_rate": stats.accuracy_rate,
                "time_spent_seconds": stats.time_spent_seconds,
            })
        except ValueError:
            return json.dumps({
                "cards_reviewed": 0,
                "accuracy_rate": 0.0,
                "time_spent_seconds": 0.0,
            })

    @Slot()
    def refreshStats(self) -> None:  # noqa: N802
        """Refresh daily stats from the service."""
        self._refresh_daily_stats()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_current_card(self) -> None:
        """Load the current card's display data from the service."""
        if self._service is None or not self._session_id:
            return

        card = self._service.get_next_card(self._session_id)
        if card is None:
            # Session complete
            self._current_word = ""
            self._current_definition = ""
            self._current_pronunciation = ""
            self._current_example = ""
            self._current_cloze_text = ""
            self._mcq_options = []
            self.cardChanged.emit()
            return

        # Look up vocabulary entry for card content
        vocab = None
        if self._vocabulary_repo is not None:
            vocab = self._vocabulary_repo.get_by_id(card.vocabulary_id)

        if vocab is not None:
            self._current_word = vocab.word
            self._current_definition = vocab.definition
            self._current_pronunciation = vocab.pronunciation or ""
            self._current_example = vocab.example_sentence or ""
        else:
            self._current_word = ""
            self._current_definition = ""
            self._current_pronunciation = ""
            self._current_example = ""

        # Mode-specific data
        if self._review_mode == CardType.CLOZE.value:
            cloze = self._service.generate_cloze_text(card.id)
            self._current_cloze_text = cloze or ""
        else:
            self._current_cloze_text = ""

        if self._review_mode == CardType.MCQ.value:
            self._mcq_options = self._service.get_multiple_choice_options(card.id)
        else:
            self._mcq_options = []

        self._card_revealed = False
        self.cardChanged.emit()

    def _refresh_daily_stats(self) -> None:
        """Reload daily stats from the service."""
        if self._service is None:
            self._due_today = 0
            self._reviewed_today = 0
            self._new_cards = 0
            self._forecast = [0] * 7
            self.statsChanged.emit()
            return

        try:
            stats = self._service.get_daily_stats()
            self._due_today = stats.due_today
            self._reviewed_today = stats.reviewed_today
            self._new_cards = stats.new_cards
            self._forecast = stats.forecast
            self.statsChanged.emit()
        except Exception as e:
            logger.exception("Failed to refresh daily stats")
            self.errorOccurred.emit(f"Failed to load stats: {e}")
