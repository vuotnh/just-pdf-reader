"""Vocabulary repository layer for VocabularyEntry, ReviewCard, and ReviewLog CRUD operations.

Provides data access for the Vocabulary Builder feature, including:
- VocabularyEntry CRUD with filtering by book, tag, and mastery level
- ReviewCard creation and cascade deletion
- ReviewLog cascade deletion
- Mastery level tracking

Requirements: 7.1–7.7
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.domain.enums import MasteryLevel
from src.domain.models import ReviewCard, ReviewLog, VocabularyEntry
from src.domain.value_objects import VocabFilter
from src.infrastructure.database.models import (
    ReviewCardModel,
    ReviewLogModel,
    TagModel,
    VocabularyEntryModel,
    vocabulary_tags,
)


class VocabularyRepository:
    """Repository for VocabularyEntry persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # VocabularyEntry CRUD
    # ------------------------------------------------------------------

    def add(self, entry: VocabularyEntry) -> VocabularyEntry:
        """Persist a new vocabulary entry to the database."""
        model = VocabularyEntryModel(
            id=entry.id,
            word=entry.word,
            definition=entry.definition,
            pronunciation=entry.pronunciation,
            part_of_speech=entry.part_of_speech,
            example_sentence=entry.example_sentence,
            book_id=entry.book_id,
            position_data=entry.position_data,
            mastery_level=entry.mastery_level.value,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return entry

    def get_by_id(self, entry_id: str) -> VocabularyEntry | None:
        """Retrieve a vocabulary entry by its ID."""
        model = self._session.get(VocabularyEntryModel, entry_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_all(self, filter: VocabFilter | None = None) -> list[VocabularyEntry]:
        """Retrieve all vocabulary entries with optional filtering.

        Entries are returned sorted by date added (most recent first).
        """
        query = self._session.query(VocabularyEntryModel)

        if filter is not None:
            query = self._apply_filter(query, filter)

        query = query.order_by(VocabularyEntryModel.created_at.desc())
        return [self._to_domain(m) for m in query.all()]

    def update(self, entry: VocabularyEntry) -> VocabularyEntry:
        """Update an existing vocabulary entry."""
        model = self._session.get(VocabularyEntryModel, entry.id)
        if model is None:
            raise ValueError(f"VocabularyEntry with id {entry.id} not found")

        model.word = entry.word
        model.definition = entry.definition
        model.pronunciation = entry.pronunciation
        model.part_of_speech = entry.part_of_speech
        model.example_sentence = entry.example_sentence
        model.book_id = entry.book_id
        model.position_data = entry.position_data
        model.mastery_level = entry.mastery_level.value
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_domain(model)

    def delete(self, entry_id: str) -> bool:
        """Delete a vocabulary entry by its ID with cascade (review cards, review logs).

        Returns True if deleted, False if not found.
        """
        model = self._session.get(VocabularyEntryModel, entry_id)
        if model is None:
            return False
        # SQLAlchemy cascade handles review cards and review logs deletion.
        self._session.delete(model)
        self._session.flush()
        return True

    def update_mastery_level(self, entry_id: str, level: MasteryLevel) -> bool:
        """Update the mastery level for a vocabulary entry.

        Returns True if updated, False if not found.
        """
        model = self._session.get(VocabularyEntryModel, entry_id)
        if model is None:
            return False
        model.mastery_level = level.value
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filter(self, query, filter: VocabFilter):
        """Apply filter criteria to a query."""
        if filter.book_id is not None:
            query = query.filter(VocabularyEntryModel.book_id == filter.book_id)

        if filter.mastery_level is not None:
            query = query.filter(
                VocabularyEntryModel.mastery_level == filter.mastery_level.value
            )

        if filter.tag is not None:
            query = query.join(VocabularyEntryModel.tags).filter(
                TagModel.name == filter.tag
            )

        return query

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def add_tag(self, entry_id: str, tag_name: str) -> bool:
        """Add a tag to a vocabulary entry. Creates the tag if it doesn't exist.

        Returns True if the tag was added, False if entry not found.
        """
        model = self._session.get(VocabularyEntryModel, entry_id)
        if model is None:
            return False

        tag = self._session.query(TagModel).filter(TagModel.name == tag_name).first()
        if tag is None:
            tag = TagModel(id=str(uuid.uuid4()), name=tag_name)
            self._session.add(tag)

        if tag not in model.tags:
            model.tags.append(tag)

        self._session.flush()
        return True

    def remove_tag(self, entry_id: str, tag_name: str) -> bool:
        """Remove a tag from a vocabulary entry.

        Returns True if removed, False if entry or tag not found.
        """
        model = self._session.get(VocabularyEntryModel, entry_id)
        if model is None:
            return False

        tag = self._session.query(TagModel).filter(TagModel.name == tag_name).first()
        if tag is None:
            return False

        if tag in model.tags:
            model.tags.remove(tag)
            self._session.flush()
            return True
        return False

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_domain(self, model: VocabularyEntryModel) -> VocabularyEntry:
        """Convert an ORM model to a domain entity."""
        return VocabularyEntry(
            id=model.id,
            word=model.word,
            definition=model.definition or "",
            pronunciation=model.pronunciation,
            part_of_speech=model.part_of_speech,
            example_sentence=model.example_sentence,
            book_id=model.book_id,
            position_data=model.position_data,
            mastery_level=MasteryLevel(model.mastery_level),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class ReviewCardRepository:
    """Repository for ReviewCard persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, card: ReviewCard) -> ReviewCard:
        """Persist a new review card to the database."""
        model = ReviewCardModel(
            id=card.id,
            vocabulary_id=card.vocabulary_id,
            card_type=card.card_type.value,
            difficulty=card.difficulty,
            stability=card.stability,
            ease_factor=card.ease_factor,
            repetitions=card.repetitions,
            last_interval=card.last_interval,
            due_date=card.due_date,
            algorithm=card.algorithm.value,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return card

    def get_by_id(self, card_id: str) -> ReviewCard | None:
        """Retrieve a review card by its ID."""
        model = self._session.get(ReviewCardModel, card_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_by_vocabulary_id(self, vocabulary_id: str) -> list[ReviewCard]:
        """Retrieve all review cards for a vocabulary entry."""
        models = (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.vocabulary_id == vocabulary_id)
            .all()
        )
        return [self._to_domain(m) for m in models]

    def get_due_cards(self, due_before: datetime | None = None) -> list[ReviewCard]:
        """Retrieve all review cards that are due for review.

        Args:
            due_before: If provided, only return cards due before this datetime.
                       Defaults to now (all currently due cards).
        """
        if due_before is None:
            due_before = datetime.now(UTC)

        models = (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.due_date <= due_before)
            .order_by(ReviewCardModel.due_date.asc())
            .all()
        )
        return [self._to_domain(m) for m in models]

    def update(self, card: ReviewCard) -> ReviewCard:
        """Update an existing review card in the database.

        Args:
            card: The updated ReviewCard domain object.

        Returns:
            The updated ReviewCard.

        Raises:
            ValueError: If the card does not exist.
        """
        model = self._session.get(ReviewCardModel, card.id)
        if model is None:
            raise ValueError(f"ReviewCard with id {card.id} not found")

        model.card_type = card.card_type.value
        model.difficulty = card.difficulty
        model.stability = card.stability
        model.ease_factor = card.ease_factor
        model.repetitions = card.repetitions
        model.last_interval = card.last_interval
        model.due_date = card.due_date
        model.algorithm = card.algorithm.value
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return card

    def get_all(self) -> list[ReviewCard]:
        """Retrieve all review cards."""
        models = self._session.query(ReviewCardModel).all()
        return [self._to_domain(m) for m in models]

    def get_due_today(self) -> list[ReviewCard]:
        """Retrieve cards due today (overdue + due today), ordered by due_date ascending.

        Returns overdue cards first (earliest due_date), then cards due today.
        """
        from datetime import date, time, timezone

        end_of_today = datetime.combine(
            date.today(), time.max, tzinfo=timezone.utc
        )
        models = (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.due_date <= end_of_today)
            .order_by(ReviewCardModel.due_date.asc())
            .all()
        )
        return [self._to_domain(m) for m in models]

    def count_due_today(self) -> int:
        """Count the number of cards due today (including overdue)."""
        from datetime import date, time, timezone

        end_of_today = datetime.combine(
            date.today(), time.max, tzinfo=timezone.utc
        )
        return (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.due_date <= end_of_today)
            .count()
        )

    def count_new_cards(self) -> int:
        """Count cards that have never been reviewed (repetitions == 0)."""
        return (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.repetitions == 0)
            .count()
        )

    def get_cards_due_in_range(
        self, start: datetime, end: datetime
    ) -> list[ReviewCard]:
        """Retrieve cards due within a date range.

        Args:
            start: Start of the range (inclusive).
            end: End of the range (inclusive).

        Returns:
            List of ReviewCard domain objects due within the range.
        """
        models = (
            self._session.query(ReviewCardModel)
            .filter(
                ReviewCardModel.due_date >= start,
                ReviewCardModel.due_date <= end,
            )
            .all()
        )
        return [self._to_domain(m) for m in models]

    def delete_by_vocabulary_id(self, vocabulary_id: str) -> int:
        """Delete all review cards for a vocabulary entry.

        Returns the number of cards deleted.
        """
        count = (
            self._session.query(ReviewCardModel)
            .filter(ReviewCardModel.vocabulary_id == vocabulary_id)
            .delete()
        )
        self._session.flush()
        return count

    def _to_domain(self, model: ReviewCardModel) -> ReviewCard:
        """Convert an ORM model to a domain entity."""
        from src.domain.enums import CardType, SRAlgorithm

        return ReviewCard(
            id=model.id,
            vocabulary_id=model.vocabulary_id,
            card_type=CardType(model.card_type),
            difficulty=model.difficulty,
            stability=model.stability,
            ease_factor=model.ease_factor,
            repetitions=model.repetitions,
            last_interval=model.last_interval,
            due_date=model.due_date,
            algorithm=SRAlgorithm(model.algorithm),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )



class ReviewLogRepository:
    """Repository for ReviewLog persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, log: ReviewLog) -> ReviewLog:
        """Persist a new review log entry to the database.

        Args:
            log: The ReviewLog domain object to persist.

        Returns:
            The persisted ReviewLog.
        """
        model = ReviewLogModel(
            id=log.id,
            card_id=log.card_id,
            rating=log.rating.value if isinstance(log.rating, MasteryLevel) else log.rating.name.lower(),
            elapsed_days=log.elapsed_days,
            scheduled_days=log.scheduled_days,
            review_duration_ms=log.review_duration_ms,
            reviewed_at=log.reviewed_at,
        )
        self._session.add(model)
        self._session.flush()
        return log

    def get_by_card_id(self, card_id: str) -> list[ReviewLog]:
        """Retrieve all review logs for a card, ordered by review time.

        Args:
            card_id: The card's unique ID.

        Returns:
            List of ReviewLog domain objects.
        """
        models = (
            self._session.query(ReviewLogModel)
            .filter(ReviewLogModel.card_id == card_id)
            .order_by(ReviewLogModel.reviewed_at.desc())
            .all()
        )
        return [self._log_to_domain(m) for m in models]

    def get_reviewed_today(self) -> list[ReviewLog]:
        """Retrieve all review logs from today.

        Returns:
            List of ReviewLog domain objects reviewed today.
        """
        from datetime import date, time, timezone

        start_of_today = datetime.combine(
            date.today(), time.min, tzinfo=timezone.utc
        )
        models = (
            self._session.query(ReviewLogModel)
            .filter(ReviewLogModel.reviewed_at >= start_of_today)
            .all()
        )
        return [self._log_to_domain(m) for m in models]

    def count_reviewed_today(self) -> int:
        """Count the number of reviews completed today."""
        from datetime import date, time, timezone

        start_of_today = datetime.combine(
            date.today(), time.min, tzinfo=timezone.utc
        )
        return (
            self._session.query(ReviewLogModel)
            .filter(ReviewLogModel.reviewed_at >= start_of_today)
            .count()
        )

    def _log_to_domain(self, model: ReviewLogModel) -> ReviewLog:
        """Convert an ORM model to a domain entity."""
        from src.domain.enums import Rating

        # Map stored string rating back to Rating enum
        rating_map = {
            "again": Rating.AGAIN,
            "hard": Rating.HARD,
            "good": Rating.GOOD,
            "easy": Rating.EASY,
        }
        rating = rating_map.get(model.rating, Rating.AGAIN)

        return ReviewLog(
            id=model.id,
            card_id=model.card_id,
            rating=rating,
            elapsed_days=model.elapsed_days or 0.0,
            scheduled_days=model.scheduled_days or 0.0,
            review_duration_ms=model.review_duration_ms or 0.0,
            reviewed_at=model.reviewed_at,
        )
