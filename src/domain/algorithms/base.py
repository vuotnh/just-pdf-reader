"""Base interface and types for scheduling algorithms.

Provides the shared ScheduleResult and ISchedulingAlgorithm protocol
used by both FSRS and SM2 implementations.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.domain.enums import Rating
from src.domain.models import ReviewCard


@dataclass(frozen=True)
class ScheduleResult:
    """Result of a scheduling calculation for a review card.

    Attributes:
        difficulty: Updated difficulty value (1-10 for FSRS, unused for SM2).
        stability: Updated stability value (FSRS concept, maps to interval for SM2).
        interval: Days until the next review.
        due_date: The calculated next review date.
        retrievability: Probability of recall at time of review (0.0 for SM2).
    """

    difficulty: float
    stability: float
    interval: float
    due_date: datetime
    retrievability: float


class ISchedulingAlgorithm(Protocol):
    """Protocol for spaced repetition scheduling algorithms.

    Implementations must provide scheduling logic that takes
    a card's current state and a user rating, then returns
    the updated schedule result.
    """

    def calculate_next_review(
        self, card: ReviewCard, rating: Rating, elapsed_days: float = 0.0
    ) -> ScheduleResult: ...

    def get_initial_intervals(self) -> list[float]: ...
