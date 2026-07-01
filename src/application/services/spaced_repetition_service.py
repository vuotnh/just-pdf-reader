"""Spaced Repetition service implementing the ISpacedRepetitionService protocol.

Orchestrates review sessions, card scheduling, algorithm dispatching, session
statistics, daily stats, algorithm switching, and review modes.

Requirements: 8.1–8.7
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from enum import Enum

from src.domain.algorithms.base import ScheduleResult
from src.domain.algorithms.fsrs import FSRSAlgorithm
from src.domain.algorithms.sm2 import SM2Algorithm
from src.domain.enums import CardType, MasteryLevel, Rating, SRAlgorithm
from src.domain.models import ReviewCard, ReviewLog
from src.domain.value_objects import DeckFilter
from src.infrastructure.repositories.vocabulary_repository import (
    ReviewCardRepository,
    ReviewLogRepository,
    VocabularyRepository,
)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ReviewSession:
    """An active review session with ordered cards and tracking state."""

    id: str
    cards: list[ReviewCard]
    current_index: int = 0
    cards_reviewed: int = 0
    correct_count: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    review_mode: CardType = CardType.FLASHCARD

    @property
    def is_complete(self) -> bool:
        """Whether all cards in the session have been reviewed."""
        return self.current_index >= len(self.cards)

    @property
    def total_cards(self) -> int:
        """Total number of cards in this session."""
        return len(self.cards)


@dataclass
class SessionStats:
    """Statistics for a completed or in-progress review session."""

    cards_reviewed: int
    accuracy_rate: float  # 0.0 to 1.0
    time_spent_seconds: float


@dataclass
class DailyStats:
    """Daily review statistics for the dashboard."""

    due_today: int
    reviewed_today: int
    new_cards: int
    forecast: list[int]  # 7-day forecast: cards due each of the next 7 days


# ---------------------------------------------------------------------------
# Service implementation
# ---------------------------------------------------------------------------


class SpacedRepetitionService:
    """Application-layer service for spaced repetition review sessions.

    Implements the ISpacedRepetitionService protocol from the design document,
    coordinating:
    - Review session creation with card ordering (overdue first, then due today)
    - Card rating dispatched to the selected algorithm (FSRS or SM2)
    - Session statistics (cards reviewed, accuracy, time spent)
    - Daily stats (due today, reviewed, new cards, 7-day forecast)
    - Algorithm switching with schedule recalculation
    - Review modes: flashcard, multiple choice, typing, cloze deletion
    """

    def __init__(
        self,
        review_card_repo: ReviewCardRepository,
        review_log_repo: ReviewLogRepository,
        vocabulary_repo: VocabularyRepository,
    ) -> None:
        self._review_card_repo = review_card_repo
        self._review_log_repo = review_log_repo
        self._vocabulary_repo = vocabulary_repo

        # Algorithm instances
        self._fsrs = FSRSAlgorithm()
        self._sm2 = SM2Algorithm()

        # Active sessions keyed by session ID
        self._active_sessions: dict[str, ReviewSession] = {}

    # ------------------------------------------------------------------
    # Session management (Requirement 8.2)
    # ------------------------------------------------------------------

    def start_session(
        self,
        deck_filter: DeckFilter | None = None,
        review_mode: CardType = CardType.FLASHCARD,
    ) -> ReviewSession:
        """Start a new review session with cards ordered by priority.

        Cards are ordered: overdue first (earliest due_date), then due today.
        An optional deck filter can restrict cards by book, tag, mastery level,
        or card type.

        Args:
            deck_filter: Optional filter to restrict which cards are included.
            review_mode: The review mode for this session (default: flashcard).

        Returns:
            A ReviewSession with the ordered card list.
        """
        # Get all cards due today (includes overdue)
        cards = self._review_card_repo.get_due_today()

        # Apply deck filter if provided
        if deck_filter is not None:
            cards = self._apply_deck_filter(cards, deck_filter)

        # Cards are already ordered by due_date ascending (overdue first)
        session = ReviewSession(
            id=str(uuid.uuid4()),
            cards=cards,
            current_index=0,
            cards_reviewed=0,
            correct_count=0,
            start_time=datetime.now(UTC),
            review_mode=review_mode,
        )

        self._active_sessions[session.id] = session
        return session

    def get_next_card(self, session_id: str) -> ReviewCard | None:
        """Get the next card to review in the session.

        Args:
            session_id: The active session ID.

        Returns:
            The next ReviewCard, or None if the session is complete.

        Raises:
            ValueError: If the session ID is not found.
        """
        session = self._get_session(session_id)
        if session.is_complete:
            return None
        return session.cards[session.current_index]

    # ------------------------------------------------------------------
    # Card rating (Requirement 8.3)
    # ------------------------------------------------------------------

    def rate_card(
        self,
        card_id: str,
        rating: Rating,
        session_id: str | None = None,
        review_duration_ms: float = 0.0,
    ) -> ScheduleResult:
        """Rate a card and dispatch to the appropriate scheduling algorithm.

        Updates the card's schedule based on the selected algorithm (FSRS or SM2),
        logs the review, and advances the session if one is active.

        Args:
            card_id: The review card ID.
            rating: The user's rating (Again, Hard, Good, Easy).
            session_id: Optional session ID to update session progress.
            review_duration_ms: Time spent reviewing this card in milliseconds.

        Returns:
            The ScheduleResult from the algorithm.

        Raises:
            ValueError: If the card is not found.
        """
        card = self._review_card_repo.get_by_id(card_id)
        if card is None:
            raise ValueError(f"ReviewCard '{card_id}' not found.")

        # Calculate elapsed days since last review
        elapsed_days = self._calculate_elapsed_days(card)

        # Dispatch to the appropriate algorithm
        result = self._dispatch_algorithm(card, rating, elapsed_days)

        # Update the card with new schedule
        updated_card = self._apply_schedule_result(card, result, rating)
        self._review_card_repo.update(updated_card)

        # Log the review
        self._create_review_log(
            card_id=card_id,
            rating=rating,
            elapsed_days=elapsed_days,
            scheduled_days=result.interval,
            review_duration_ms=review_duration_ms,
        )

        # Update mastery level based on repetitions
        self._update_mastery_level(card)

        # Advance session if applicable
        if session_id is not None:
            self._advance_session(session_id, rating)

        return result

    # ------------------------------------------------------------------
    # Session statistics (Requirement 8.5)
    # ------------------------------------------------------------------

    def get_session_stats(self, session_id: str) -> SessionStats:
        """Get statistics for a review session.

        Args:
            session_id: The session ID.

        Returns:
            SessionStats with cards reviewed, accuracy, and time spent.

        Raises:
            ValueError: If the session ID is not found.
        """
        session = self._get_session(session_id)
        now = datetime.now(UTC)
        time_spent = (now - session.start_time).total_seconds()

        accuracy = 0.0
        if session.cards_reviewed > 0:
            accuracy = session.correct_count / session.cards_reviewed

        return SessionStats(
            cards_reviewed=session.cards_reviewed,
            accuracy_rate=accuracy,
            time_spent_seconds=time_spent,
        )

    def end_session(self, session_id: str) -> SessionStats:
        """End a review session and return final statistics.

        Args:
            session_id: The session ID.

        Returns:
            Final SessionStats for the session.

        Raises:
            ValueError: If the session ID is not found.
        """
        stats = self.get_session_stats(session_id)
        # Remove the session from active sessions
        self._active_sessions.pop(session_id, None)
        return stats

    # ------------------------------------------------------------------
    # Daily stats (Requirement 8.6)
    # ------------------------------------------------------------------

    def get_daily_stats(self) -> DailyStats:
        """Get daily review statistics for the dashboard.

        Returns:
            DailyStats with due today, reviewed today, new cards,
            and 7-day forecast.
        """
        due_today = self._review_card_repo.count_due_today()
        reviewed_today = self._review_log_repo.count_reviewed_today()
        new_cards = self._review_card_repo.count_new_cards()
        forecast = self._calculate_7day_forecast()

        return DailyStats(
            due_today=due_today,
            reviewed_today=reviewed_today,
            new_cards=new_cards,
            forecast=forecast,
        )

    # ------------------------------------------------------------------
    # Algorithm switching (Requirement 8.7)
    # ------------------------------------------------------------------

    def switch_algorithm(self, algorithm: SRAlgorithm) -> None:
        """Switch the scheduling algorithm and recalculate all pending schedules.

        Recalculates due dates for all cards using the new algorithm's
        interval calculation based on current card state.

        Args:
            algorithm: The algorithm to switch to (SM2 or FSRS).
        """
        all_cards = self._review_card_repo.get_all()

        for card in all_cards:
            if card.algorithm == algorithm:
                continue

            # Update the card's algorithm
            card.algorithm = algorithm

            # Recalculate the schedule using the new algorithm
            recalculated = self._recalculate_schedule(card, algorithm)
            self._review_card_repo.update(recalculated)

    # ------------------------------------------------------------------
    # Review modes (Requirement 8.4)
    # ------------------------------------------------------------------

    def set_review_mode(self, session_id: str, mode: CardType) -> None:
        """Change the review mode for an active session.

        Supported modes: flashcard, multiple choice, typing, cloze deletion.

        Args:
            session_id: The active session ID.
            mode: The new review mode.

        Raises:
            ValueError: If the session ID is not found.
        """
        session = self._get_session(session_id)
        session.review_mode = mode

    def get_review_mode(self, session_id: str) -> CardType:
        """Get the current review mode for a session.

        Args:
            session_id: The active session ID.

        Returns:
            The current CardType review mode.

        Raises:
            ValueError: If the session ID is not found.
        """
        session = self._get_session(session_id)
        return session.review_mode

    def get_multiple_choice_options(
        self, card_id: str, num_options: int = 4
    ) -> list[str]:
        """Generate multiple choice options for a card.

        Returns the correct definition plus distractor definitions
        from other vocabulary entries.

        Args:
            card_id: The review card ID.
            num_options: Number of options to generate (default 4).

        Returns:
            List of definition strings (including the correct one).

        Raises:
            ValueError: If the card is not found.
        """
        card = self._review_card_repo.get_by_id(card_id)
        if card is None:
            raise ValueError(f"ReviewCard '{card_id}' not found.")

        # Get the correct answer
        vocab_entry = self._vocabulary_repo.get_by_id(card.vocabulary_id)
        if vocab_entry is None:
            return []

        correct_definition = vocab_entry.definition

        # Get distractor definitions from other vocabulary entries
        all_entries = self._vocabulary_repo.get_all()
        distractors: list[str] = []
        for entry in all_entries:
            if entry.id != card.vocabulary_id and entry.definition:
                distractors.append(entry.definition)
            if len(distractors) >= num_options - 1:
                break

        # Combine and shuffle (put correct answer at random position)
        import random

        options = [correct_definition] + distractors[: num_options - 1]
        random.shuffle(options)
        return options

    def generate_cloze_text(self, card_id: str) -> str | None:
        """Generate cloze deletion text for a card.

        Replaces the word in the example sentence with a blank.

        Args:
            card_id: The review card ID.

        Returns:
            The example sentence with the word replaced by '{{c1::...}}',
            or None if no example sentence is available.

        Raises:
            ValueError: If the card is not found.
        """
        card = self._review_card_repo.get_by_id(card_id)
        if card is None:
            raise ValueError(f"ReviewCard '{card_id}' not found.")

        vocab_entry = self._vocabulary_repo.get_by_id(card.vocabulary_id)
        if vocab_entry is None or not vocab_entry.example_sentence:
            return None

        # Replace the word with cloze deletion marker
        word = vocab_entry.word
        sentence = vocab_entry.example_sentence

        # Case-insensitive replacement
        import re

        pattern = re.compile(re.escape(word), re.IGNORECASE)
        cloze_text = pattern.sub(f"{{{{c1::{word}}}}}", sentence, count=1)

        return cloze_text

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_session(self, session_id: str) -> ReviewSession:
        """Retrieve an active session or raise ValueError."""
        session = self._active_sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found or has ended.")
        return session

    def _apply_deck_filter(
        self, cards: list[ReviewCard], deck_filter: DeckFilter
    ) -> list[ReviewCard]:
        """Apply deck filter criteria to a list of cards.

        Filters by book_id, tag, mastery_level, or card_types by
        checking the associated vocabulary entry.
        """
        filtered: list[ReviewCard] = []

        for card in cards:
            # Filter by card type
            if deck_filter.card_types:
                if card.card_type.value not in deck_filter.card_types:
                    continue

            # Filter by book_id or mastery_level requires vocabulary lookup
            if deck_filter.book_id is not None or deck_filter.mastery_level is not None:
                vocab = self._vocabulary_repo.get_by_id(card.vocabulary_id)
                if vocab is None:
                    continue

                if deck_filter.book_id is not None and vocab.book_id != deck_filter.book_id:
                    continue

                if deck_filter.mastery_level is not None and vocab.mastery_level != deck_filter.mastery_level:
                    continue

            filtered.append(card)

        return filtered

    def _dispatch_algorithm(
        self, card: ReviewCard, rating: Rating, elapsed_days: float
    ) -> ScheduleResult:
        """Dispatch the rating to the appropriate algorithm based on card settings.

        Args:
            card: The review card.
            rating: The user's rating.
            elapsed_days: Days since last review.

        Returns:
            ScheduleResult from the selected algorithm.
        """
        if card.algorithm == SRAlgorithm.SM2:
            return self._sm2.calculate_next_review(card, rating, elapsed_days)
        else:
            return self._fsrs.calculate_next_review(card, rating, elapsed_days)

    def _calculate_elapsed_days(self, card: ReviewCard) -> float:
        """Calculate days since the card was last reviewed.

        Uses the card's updated_at timestamp as proxy for last review time.
        """
        now = datetime.now(UTC)
        delta = now - card.updated_at
        return max(0.0, delta.total_seconds() / 86400.0)

    def _apply_schedule_result(
        self, card: ReviewCard, result: ScheduleResult, rating: Rating
    ) -> ReviewCard:
        """Apply a ScheduleResult to update a ReviewCard's fields.

        Args:
            card: The original card.
            result: The algorithm's schedule result.
            rating: The user's rating.

        Returns:
            The updated ReviewCard with new schedule values.
        """
        now = datetime.now(UTC)

        card.difficulty = result.difficulty
        card.stability = result.stability
        card.last_interval = result.interval
        card.due_date = result.due_date
        card.updated_at = now

        # For SM2: update ease_factor and repetitions
        if card.algorithm == SRAlgorithm.SM2:
            # SM2 stores interval as stability for compatibility
            card.ease_factor = max(1.3, card.ease_factor + (
                0.1 - (5 - self._rating_to_quality(rating)) *
                (0.08 + (5 - self._rating_to_quality(rating)) * 0.02)
            ))
            if self._rating_to_quality(rating) >= 3:
                card.repetitions += 1
            else:
                card.repetitions = 0

        return card

    def _rating_to_quality(self, rating: Rating) -> int:
        """Map Rating enum to SM2 quality score (0-5 scale)."""
        mapping = {
            Rating.AGAIN: 0,
            Rating.HARD: 2,
            Rating.GOOD: 3,
            Rating.EASY: 5,
        }
        return mapping[rating]

    def _create_review_log(
        self,
        card_id: str,
        rating: Rating,
        elapsed_days: float,
        scheduled_days: float,
        review_duration_ms: float,
    ) -> None:
        """Create and persist a review log entry."""
        log = ReviewLog(
            id=str(uuid.uuid4()),
            card_id=card_id,
            rating=rating,
            elapsed_days=elapsed_days,
            scheduled_days=scheduled_days,
            review_duration_ms=review_duration_ms,
            reviewed_at=datetime.now(UTC),
        )
        self._review_log_repo.add(log)

    def _advance_session(self, session_id: str, rating: Rating) -> None:
        """Advance the session state after a card is reviewed.

        Increments the current card index, updates reviewed count,
        and tracks accuracy (Good/Easy = correct).
        """
        session = self._active_sessions.get(session_id)
        if session is None:
            return

        session.cards_reviewed += 1
        session.current_index += 1

        # Good and Easy are considered correct answers
        if rating in (Rating.GOOD, Rating.EASY):
            session.correct_count += 1

    def _update_mastery_level(self, card: ReviewCard) -> None:
        """Update the vocabulary entry's mastery level based on card state.

        Mastery progression:
        - New: 0 repetitions
        - Learning: 1-2 repetitions
        - Reviewing: 3+ repetitions with stability < threshold
        - Mastered: high stability (> 30 days for FSRS) or many repetitions
        """
        vocab = self._vocabulary_repo.get_by_id(card.vocabulary_id)
        if vocab is None:
            return

        if card.repetitions == 0:
            new_level = MasteryLevel.NEW
        elif card.repetitions <= 2:
            new_level = MasteryLevel.LEARNING
        elif card.algorithm == SRAlgorithm.FSRS and card.stability > 30.0:
            new_level = MasteryLevel.MASTERED
        elif card.algorithm == SRAlgorithm.SM2 and card.repetitions >= 8:
            new_level = MasteryLevel.MASTERED
        else:
            new_level = MasteryLevel.REVIEWING

        if vocab.mastery_level != new_level:
            self._vocabulary_repo.update_mastery_level(card.vocabulary_id, new_level)

    def _recalculate_schedule(
        self, card: ReviewCard, algorithm: SRAlgorithm
    ) -> ReviewCard:
        """Recalculate a card's schedule when switching algorithms.

        For FSRS → SM2: maps stability to interval, sets default ease factor.
        For SM2 → FSRS: maps interval to stability, sets default difficulty.

        Args:
            card: The card to recalculate.
            algorithm: The new algorithm.

        Returns:
            The card with updated schedule fields.
        """
        now = datetime.now(UTC)

        if algorithm == SRAlgorithm.SM2:
            # Moving to SM2: use current interval, set default ease factor
            interval = card.last_interval if card.last_interval > 0 else 1.0
            card.ease_factor = max(card.ease_factor, 2.5)
            card.due_date = now + timedelta(days=interval)
        else:
            # Moving to FSRS: use current interval as stability estimate
            if card.last_interval > 0:
                card.stability = card.last_interval
            else:
                card.stability = 0.4  # Default for new cards
            card.difficulty = 5.0  # Default midpoint
            interval = self._fsrs._calculate_interval(card.stability)
            interval = max(1.0, round(interval))
            card.due_date = now + timedelta(days=interval)
            card.last_interval = interval

        card.algorithm = algorithm
        card.updated_at = now
        return card

    def _calculate_7day_forecast(self) -> list[int]:
        """Calculate a 7-day review forecast.

        For each of the next 7 days, counts how many cards are due.

        Returns:
            List of 7 integers representing cards due on each day.
        """
        forecast: list[int] = []
        today = date.today()

        for day_offset in range(1, 8):
            target_date = today + timedelta(days=day_offset)
            start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
            end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
            cards = self._review_card_repo.get_cards_due_in_range(start, end)
            forecast.append(len(cards))

        return forecast
