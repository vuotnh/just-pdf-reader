"""FSRS (Free Spaced Repetition Scheduler) algorithm implementation.

Implements the FSRS-4.5 algorithm based on the DSR (Difficulty-Stability-Retrievability)
memory model. This is the default scheduling algorithm for the platform.

Reference: https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import exp
from typing import Protocol

from src.domain.enums import Rating
from src.domain.models import ReviewCard


# Default FSRS-4.5 parameters (17 weights)
DEFAULT_WEIGHTS: list[float] = [
    0.4,    # w[0]: initial stability for Again
    0.6,    # w[1]: initial stability for Hard
    2.4,    # w[2]: initial stability for Good
    5.8,    # w[3]: initial stability for Easy
    4.93,   # w[4]: difficulty base (unused in simplified model)
    0.94,   # w[5]: difficulty multiplier (unused in simplified model)
    0.86,   # w[6]: difficulty update factor
    0.01,   # w[7]: difficulty reversion factor (unused in simplified model)
    1.49,   # w[8]: stability increase base
    0.14,   # w[9]: stability-difficulty interaction
    0.94,   # w[10]: stability-retrievability interaction
    2.18,   # w[11]: forget stability base
    0.05,   # w[12]: forget difficulty interaction
    0.34,   # w[13]: forget stability interaction
    1.26,   # w[14]: forget retrievability interaction
    0.29,   # w[15]: hard multiplier
    2.61,   # w[16]: easy multiplier
]

DEFAULT_DESIRED_RETENTION: float = 0.9


@dataclass(frozen=True)
class ScheduleResult:
    """Result of a scheduling calculation for a review card."""

    difficulty: float
    stability: float
    interval: float  # days until next review
    due_date: datetime
    retrievability: float


class ISchedulingAlgorithm(Protocol):
    """Protocol for spaced repetition scheduling algorithms."""

    def calculate_next_review(
        self, card: ReviewCard, rating: Rating, elapsed_days: float = 0.0
    ) -> ScheduleResult: ...

    def get_initial_intervals(self) -> list[float]: ...


class FSRSAlgorithm:
    """FSRS-4.5 scheduling algorithm implementation.

    Uses the DSR (Difficulty-Stability-Retrievability) memory model to
    calculate optimal review intervals based on desired retention rate.
    """

    def __init__(
        self,
        weights: list[float] | None = None,
        desired_retention: float = DEFAULT_DESIRED_RETENTION,
    ) -> None:
        self.w = weights if weights is not None else DEFAULT_WEIGHTS.copy()
        self.desired_retention = desired_retention

    def calculate_retrievability(self, elapsed_days: float, stability: float) -> float:
        """Calculate the probability of recall at a given time.

        R(t, S) = (1 + t / (9 * S))^(-1)

        Args:
            elapsed_days: Days since last review.
            stability: Current stability value (days for R to drop to 90%).

        Returns:
            Retrievability value in range (0, 1].
        """
        if stability <= 0:
            return 0.0
        return (1.0 + elapsed_days / (9.0 * stability)) ** (-1)

    def calculate_next_review(
        self, card: ReviewCard, rating: Rating, elapsed_days: float = 0.0
    ) -> ScheduleResult:
        """Calculate the next review schedule based on current card state and rating.

        Args:
            card: Current review card state.
            rating: User's rating for this review.
            elapsed_days: Days since the card was last reviewed.

        Returns:
            ScheduleResult with updated difficulty, stability, interval, and due date.
        """
        difficulty = card.difficulty
        stability = card.stability

        # For new cards (stability near zero), use initial stability
        if stability < 0.01:
            new_stability = self._initial_stability(rating)
            new_difficulty = self._initial_difficulty(rating)
            interval = self._calculate_interval(new_stability)
            retrievability = 0.0
        else:
            retrievability = self.calculate_retrievability(elapsed_days, stability)
            new_difficulty = self._update_difficulty(difficulty, rating)

            if rating == Rating.AGAIN:
                new_stability = self._stability_after_forget(
                    difficulty, stability, retrievability
                )
            else:
                new_stability = self._stability_after_recall(
                    difficulty, stability, retrievability, rating
                )

            interval = self._calculate_interval(new_stability)

        # Ensure minimum interval of 1 day
        interval = max(1.0, round(interval))

        due_date = datetime.now(UTC) + timedelta(days=interval)

        return ScheduleResult(
            difficulty=new_difficulty,
            stability=new_stability,
            interval=interval,
            due_date=due_date,
            retrievability=retrievability,
        )

    def get_initial_intervals(self) -> list[float]:
        """Get initial intervals for each rating (Again, Hard, Good, Easy).

        Returns:
            List of 4 intervals in days, one per rating.
        """
        intervals = []
        for rating in [Rating.AGAIN, Rating.HARD, Rating.GOOD, Rating.EASY]:
            stability = self._initial_stability(rating)
            interval = max(1.0, round(self._calculate_interval(stability)))
            intervals.append(interval)
        return intervals

    def _initial_stability(self, rating: Rating) -> float:
        """Get initial stability for a new card based on first rating.

        S_0(rating) = w[rating - 1]

        Args:
            rating: The first rating given to a new card.

        Returns:
            Initial stability value.
        """
        return self.w[rating.value - 1]

    def _initial_difficulty(self, rating: Rating) -> float:
        """Calculate initial difficulty for a new card based on first rating.

        Uses the difficulty update formula centered around the default difficulty
        of 5.0 (middle of the 1-10 range).

        Args:
            rating: The first rating given to a new card.

        Returns:
            Initial difficulty value clamped to [1, 10].
        """
        # Start at midpoint difficulty, adjust by rating distance from Good (3)
        initial_d = 5.0 - self.w[6] * (rating.value - 3)
        return self._clamp_difficulty(initial_d)

    def _update_difficulty(self, difficulty: float, rating: Rating) -> float:
        """Update difficulty based on the rating.

        D'(D, rating) = D - w[6] * (rating - 3)
        D' = clamp(D', 1, 10)

        Args:
            difficulty: Current difficulty.
            rating: User's rating.

        Returns:
            Updated difficulty clamped to [1, 10].
        """
        new_difficulty = difficulty - self.w[6] * (rating.value - 3)
        return self._clamp_difficulty(new_difficulty)

    def _stability_after_recall(
        self,
        difficulty: float,
        stability: float,
        retrievability: float,
        rating: Rating,
    ) -> float:
        """Calculate new stability after a successful review (Hard, Good, or Easy).

        S'_recall(D, S, R, rating) = S * (1 + exp(w[8]) *
            (11 - D) * S^(-w[9]) * (exp(w[10] * (1 - R)) - 1) *
            rating_multiplier)

        Args:
            difficulty: Current difficulty.
            stability: Current stability.
            retrievability: Current retrievability at time of review.
            rating: Must be Hard, Good, or Easy.

        Returns:
            Updated stability value.
        """
        rating_multiplier = self._get_rating_multiplier(rating)

        new_stability = stability * (
            1.0
            + exp(self.w[8])
            * (11.0 - difficulty)
            * stability ** (-self.w[9])
            * (exp(self.w[10] * (1.0 - retrievability)) - 1.0)
            * rating_multiplier
        )

        return max(0.01, new_stability)

    def _stability_after_forget(
        self, difficulty: float, stability: float, retrievability: float
    ) -> float:
        """Calculate new stability after a failed review (Again).

        S'_forget(D, S, R) = w[11] * D^(-w[12]) * ((S + 1)^w[13] - 1) *
                             exp(w[14] * (1 - R))

        Args:
            difficulty: Current difficulty.
            stability: Current stability.
            retrievability: Current retrievability at time of review.

        Returns:
            Updated stability value (will be less than current stability).
        """
        new_stability = (
            self.w[11]
            * difficulty ** (-self.w[12])
            * ((stability + 1.0) ** self.w[13] - 1.0)
            * exp(self.w[14] * (1.0 - retrievability))
        )

        # Ensure stability doesn't exceed current (forgetting should reduce it)
        # and has a minimum floor
        return max(0.01, min(new_stability, stability))

    def _calculate_interval(self, stability: float) -> float:
        """Calculate the interval from stability and desired retention.

        Derived from R(t, S) = (1 + t/(9*S))^(-1), solving for t when R = desired_retention:
        t = S * 9 * (1/desired_retention - 1)

        Args:
            stability: Current stability value.

        Returns:
            Interval in days.
        """
        if self.desired_retention <= 0 or self.desired_retention >= 1:
            return stability * 9.0 * (1.0 / DEFAULT_DESIRED_RETENTION - 1.0)

        return stability * 9.0 * (1.0 / self.desired_retention - 1.0)

    def _get_rating_multiplier(self, rating: Rating) -> float:
        """Get the rating-specific multiplier for stability calculation.

        Hard uses w[15], Good uses 1.0 (baseline), Easy uses w[16].

        Args:
            rating: The user's rating (Hard, Good, or Easy).

        Returns:
            Multiplier value.
        """
        if rating == Rating.HARD:
            return self.w[15]
        elif rating == Rating.EASY:
            return self.w[16]
        # Good is the baseline
        return 1.0

    @staticmethod
    def _clamp_difficulty(difficulty: float) -> float:
        """Clamp difficulty to the valid range [1, 10].

        Args:
            difficulty: Raw difficulty value.

        Returns:
            Clamped difficulty value.
        """
        return max(1.0, min(10.0, difficulty))
