"""SM2 (SuperMemo 2) spaced repetition scheduling algorithm.

Implements the classic SuperMemo 2 algorithm by Piotr Wozniak.
The algorithm uses an ease factor (EF) that adjusts based on
response quality to determine review intervals.

SM2 interval progression:
- First successful review: 1 day
- Second successful review: 6 days
- Subsequent reviews: previous_interval * ease_factor

On failure (Again rating), repetitions reset to 0 and interval
resets to 1 day.

The ease factor has a minimum floor of 1.3 to prevent intervals
from shrinking too aggressively.

Reference: https://www.supermemo.com/en/archives1990-2015/english/ol/sm2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.algorithms.base import ScheduleResult
from src.domain.enums import Rating
from src.domain.models import ReviewCard

# Minimum ease factor to prevent intervals from collapsing
_MIN_EASE_FACTOR = 1.3

# Mapping from Rating enum to SM2 quality score (0-5 scale)
_RATING_TO_QUALITY: dict[Rating, int] = {
    Rating.AGAIN: 0,
    Rating.HARD: 2,
    Rating.GOOD: 3,
    Rating.EASY: 5,
}

# Quality threshold for a passing response
_PASS_THRESHOLD = 3


class SM2Algorithm:
    """SuperMemo 2 scheduling algorithm implementation.

    Uses ease factor and repetition count to determine
    progressively longer review intervals for successful recalls,
    with reset on failure.
    """

    def calculate_next_review(
        self, card: ReviewCard, rating: Rating, elapsed_days: float = 0.0
    ) -> ScheduleResult:
        """Calculate the next review schedule for a card.

        The SM2 algorithm works as follows:
        - Maps the user rating to a quality score (0-5 scale)
        - If quality >= 3 (pass): advance the interval based on repetition count
        - If quality < 3 (fail): reset repetitions and interval to 1 day
        - Update ease factor with floor at 1.3

        Args:
            card: The current state of the review card.
            rating: The user's rating of their recall quality.
            elapsed_days: Days since last review (unused by SM2 but kept
                for interface compatibility with FSRS).

        Returns:
            ScheduleResult with updated schedule information.
        """
        quality = _RATING_TO_QUALITY[rating]
        ease_factor = card.ease_factor
        repetitions = card.repetitions
        last_interval = card.last_interval

        if quality >= _PASS_THRESHOLD:
            # Successful recall — advance interval
            if repetitions == 0:
                interval = 1.0
            elif repetitions == 1:
                interval = 6.0
            else:
                interval = last_interval * ease_factor
            repetitions += 1
        else:
            # Failed recall — reset
            repetitions = 0
            interval = 1.0

        # Update ease factor using SM2 formula:
        # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        ease_factor = ease_factor + (
            0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        )
        ease_factor = max(ease_factor, _MIN_EASE_FACTOR)

        due_date = datetime.now(UTC) + timedelta(days=interval)

        return ScheduleResult(
            difficulty=0.0,  # SM2 does not use difficulty
            stability=interval,  # Map interval as stability for compatibility
            interval=interval,
            due_date=due_date,
            retrievability=0.0,  # SM2 does not calculate retrievability
        )

    def get_initial_intervals(self) -> list[float]:
        """Return the initial interval sequence for SM2.

        For SM2, the first review always gets 1 day regardless of rating
        (since repetitions=0), and the second review gets 6 days.

        Returns:
            List of initial intervals [1 day, 6 days].
        """
        return [1.0, 6.0]

    @staticmethod
    def compute_ease_factor(current_ef: float, quality: int) -> float:
        """Compute the updated ease factor given a quality score.

        EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        EF' = max(EF', 1.3)

        This is exposed as a static method for testing and reuse.

        Args:
            current_ef: The current ease factor.
            quality: Quality of response on 0-5 scale.

        Returns:
            Updated ease factor, no less than 1.3.
        """
        new_ef = current_ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        return max(new_ef, _MIN_EASE_FACTOR)

    @staticmethod
    def compute_interval(
        repetitions: int, last_interval: float, ease_factor: float
    ) -> float:
        """Compute the next interval based on repetition count.

        - repetitions == 0: 1 day
        - repetitions == 1: 6 days
        - repetitions >= 2: last_interval * ease_factor

        Args:
            repetitions: Number of consecutive successful reviews.
            last_interval: The previous interval in days.
            ease_factor: The current ease factor.

        Returns:
            Next interval in days.
        """
        if repetitions == 0:
            return 1.0
        elif repetitions == 1:
            return 6.0
        else:
            return last_interval * ease_factor
