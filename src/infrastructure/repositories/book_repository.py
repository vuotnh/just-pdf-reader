"""Library repository layer for Book, Collection, and Tag CRUD operations.

Provides data access for the Library Manager feature, including:
- Book CRUD with sorting and filtering
- Collection management (create, add/remove books)
- Tag management (create, associate with books)
- Reading history recording and last-read position persistence
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.enums import SortCriterion
from src.domain.models import Book, Collection, ReadingHistory, Tag
from src.domain.value_objects import BookFilter, ReadingPosition
from src.infrastructure.database.models import (
    BookModel,
    CollectionModel,
    ReadingHistoryModel,
    TagModel,
    book_collections,
    book_tags,
)


class BookRepository:
    """Repository for Book persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Book CRUD
    # ------------------------------------------------------------------

    def add(self, book: Book) -> Book:
        """Persist a new book to the database."""
        model = BookModel(
            id=book.id,
            title=book.title,
            author=book.author,
            publisher=book.publisher,
            language=book.language,
            page_count=book.page_count,
            file_path=book.file_path,
            file_hash=book.file_hash,
            format=book.format.value,
            cover_image=book.cover_image,
            is_favorite=book.is_favorite,
            created_at=book.created_at,
            updated_at=book.updated_at,
        )
        self._session.add(model)
        self._session.flush()
        return book

    def get_by_id(self, book_id: str) -> Book | None:
        """Retrieve a book by its ID."""
        model = self._session.get(BookModel, book_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_all(
        self,
        sort_by: SortCriterion = SortCriterion.DATE_ADDED,
        filter: BookFilter | None = None,
    ) -> list[Book]:
        """Retrieve all books with optional sorting and filtering."""
        query = self._session.query(BookModel)

        # Apply filters
        if filter is not None:
            query = self._apply_filter(query, filter)

        # Apply sorting
        query = self._apply_sort(query, sort_by)

        return [self._to_domain(m) for m in query.all()]

    def update(self, book: Book) -> Book:
        """Update an existing book."""
        model = self._session.get(BookModel, book.id)
        if model is None:
            raise ValueError(f"Book with id {book.id} not found")

        model.title = book.title
        model.author = book.author
        model.publisher = book.publisher
        model.language = book.language
        model.page_count = book.page_count
        model.file_path = book.file_path
        model.file_hash = book.file_hash
        model.format = book.format.value
        model.cover_image = book.cover_image
        model.is_favorite = book.is_favorite
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return self._to_domain(model)

    def delete(self, book_id: str) -> bool:
        """Delete a book by its ID. Returns True if deleted, False if not found."""
        model = self._session.get(BookModel, book_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def set_favorite(self, book_id: str, is_favorite: bool) -> bool:
        """Set the favorite status of a book. Returns True if updated."""
        model = self._session.get(BookModel, book_id)
        if model is None:
            return False
        model.is_favorite = is_favorite
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return True

    def get_by_file_hash(self, file_hash: str) -> Book | None:
        """Find a book by its file hash (for deduplication)."""
        model = (
            self._session.query(BookModel)
            .filter(BookModel.file_hash == file_hash)
            .first()
        )
        if model is None:
            return None
        return self._to_domain(model)

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def _apply_sort(self, query, sort_by: SortCriterion):
        """Apply sorting to a query based on the criterion."""
        sort_map = {
            SortCriterion.TITLE: BookModel.title.asc(),
            SortCriterion.AUTHOR: BookModel.author.asc(),
            SortCriterion.DATE_ADDED: BookModel.created_at.desc(),
            SortCriterion.FILE_SIZE: BookModel.page_count.desc(),
        }

        if sort_by == SortCriterion.LAST_READ:
            # Sort by most recent reading history entry
            subquery = (
                self._session.query(
                    ReadingHistoryModel.book_id,
                    func.max(ReadingHistoryModel.accessed_at).label("last_read"),
                )
                .group_by(ReadingHistoryModel.book_id)
                .subquery()
            )
            query = query.outerjoin(
                subquery, BookModel.id == subquery.c.book_id
            ).order_by(subquery.c.last_read.desc().nullslast())
        else:
            order_clause = sort_map.get(sort_by, BookModel.created_at.desc())
            query = query.order_by(order_clause)

        return query

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filter(self, query, filter: BookFilter):
        """Apply filter criteria to a query."""
        if filter.is_favorite is not None:
            query = query.filter(BookModel.is_favorite == filter.is_favorite)

        if filter.format is not None:
            query = query.filter(BookModel.format == filter.format.value)

        if filter.tag is not None:
            query = query.join(BookModel.tags).filter(TagModel.name == filter.tag)

        if filter.collection_id is not None:
            query = query.join(BookModel.collections).filter(
                CollectionModel.id == filter.collection_id
            )

        return query

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def add_tag(self, book_id: str, tag_name: str) -> bool:
        """Add a tag to a book. Creates the tag if it doesn't exist.

        Returns True if the tag was added, False if book not found.
        """
        model = self._session.get(BookModel, book_id)
        if model is None:
            return False

        # Find or create tag
        tag = self._session.query(TagModel).filter(TagModel.name == tag_name).first()
        if tag is None:
            tag = TagModel(id=str(uuid.uuid4()), name=tag_name)
            self._session.add(tag)

        # Add tag association if not already present
        if tag not in model.tags:
            model.tags.append(tag)

        self._session.flush()
        return True

    def remove_tag(self, book_id: str, tag_name: str) -> bool:
        """Remove a tag from a book. Returns True if removed."""
        model = self._session.get(BookModel, book_id)
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

    def get_tags_for_book(self, book_id: str) -> list[Tag]:
        """Get all tags associated with a book."""
        model = self._session.get(BookModel, book_id)
        if model is None:
            return []
        return [Tag(id=t.id, name=t.name, color=t.color) for t in model.tags]

    # ------------------------------------------------------------------
    # Collection operations
    # ------------------------------------------------------------------

    def add_to_collection(self, book_id: str, collection_id: str) -> bool:
        """Add a book to a collection. Returns True if added."""
        book = self._session.get(BookModel, book_id)
        if book is None:
            return False

        collection = self._session.get(CollectionModel, collection_id)
        if collection is None:
            return False

        if collection not in book.collections:
            book.collections.append(collection)
            self._session.flush()
        return True

    def remove_from_collection(self, book_id: str, collection_id: str) -> bool:
        """Remove a book from a collection. Returns True if removed."""
        book = self._session.get(BookModel, book_id)
        if book is None:
            return False

        collection = self._session.get(CollectionModel, collection_id)
        if collection is None:
            return False

        if collection in book.collections:
            book.collections.remove(collection)
            self._session.flush()
            return True
        return False

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_domain(self, model: BookModel) -> Book:
        """Convert an ORM model to a domain entity."""
        from src.domain.enums import BookFormat

        return Book(
            id=model.id,
            title=model.title,
            author=model.author,
            publisher=model.publisher,
            language=model.language,
            page_count=model.page_count,
            file_path=model.file_path,
            file_hash=model.file_hash,
            format=BookFormat(model.format),
            cover_image=model.cover_image,
            is_favorite=model.is_favorite,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class CollectionRepository:
    """Repository for Collection persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, description: str | None = None) -> Collection:
        """Create a new collection."""
        collection_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        model = CollectionModel(
            id=collection_id,
            name=name,
            description=description,
            created_at=now,
        )
        self._session.add(model)
        self._session.flush()
        return Collection(
            id=collection_id,
            name=name,
            description=description,
            created_at=now,
        )

    def get_by_id(self, collection_id: str) -> Collection | None:
        """Retrieve a collection by its ID."""
        model = self._session.get(CollectionModel, collection_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_all(self) -> list[Collection]:
        """Retrieve all collections."""
        models = self._session.query(CollectionModel).order_by(CollectionModel.name).all()
        return [self._to_domain(m) for m in models]

    def delete(self, collection_id: str) -> bool:
        """Delete a collection. Returns True if deleted."""
        model = self._session.get(CollectionModel, collection_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def get_books_in_collection(self, collection_id: str) -> list[Book]:
        """Get all books in a collection."""
        model = self._session.get(CollectionModel, collection_id)
        if model is None:
            return []

        from src.domain.enums import BookFormat

        return [
            Book(
                id=b.id,
                title=b.title,
                author=b.author,
                publisher=b.publisher,
                language=b.language,
                page_count=b.page_count,
                file_path=b.file_path,
                file_hash=b.file_hash,
                format=BookFormat(b.format),
                cover_image=b.cover_image,
                is_favorite=b.is_favorite,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in model.books
        ]

    def _to_domain(self, model: CollectionModel) -> Collection:
        """Convert an ORM model to a domain entity."""
        return Collection(
            id=model.id,
            name=model.name,
            description=model.description,
            created_at=model.created_at,
        )


class TagRepository:
    """Repository for Tag persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, color: str | None = None) -> Tag:
        """Create a new tag."""
        tag_id = str(uuid.uuid4())
        model = TagModel(id=tag_id, name=name, color=color)
        self._session.add(model)
        self._session.flush()
        return Tag(id=tag_id, name=name, color=color)

    def get_by_id(self, tag_id: str) -> Tag | None:
        """Retrieve a tag by its ID."""
        model = self._session.get(TagModel, tag_id)
        if model is None:
            return None
        return Tag(id=model.id, name=model.name, color=model.color)

    def get_by_name(self, name: str) -> Tag | None:
        """Retrieve a tag by its name."""
        model = self._session.query(TagModel).filter(TagModel.name == name).first()
        if model is None:
            return None
        return Tag(id=model.id, name=model.name, color=model.color)

    def get_all(self) -> list[Tag]:
        """Retrieve all tags."""
        models = self._session.query(TagModel).order_by(TagModel.name).all()
        return [Tag(id=m.id, name=m.name, color=m.color) for m in models]

    def delete(self, tag_id: str) -> bool:
        """Delete a tag. Returns True if deleted."""
        model = self._session.get(TagModel, tag_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True


class ReadingHistoryRepository:
    """Repository for reading history and position persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record_open(self, book_id: str, position: ReadingPosition) -> ReadingHistory:
        """Record that a book was opened at a given position."""
        now = datetime.now(UTC)
        history_id = str(uuid.uuid4())

        position_json = json.dumps({
            "page": position.page,
            "chapter": position.chapter,
            "scroll_offset": position.scroll_offset,
        })

        model = ReadingHistoryModel(
            id=history_id,
            book_id=book_id,
            position_data=position_json,
            accessed_at=now,
        )
        self._session.add(model)
        self._session.flush()

        return ReadingHistory(
            id=history_id,
            book_id=book_id,
            position_data=position_json,
            accessed_at=now,
        )

    def get_last_position(self, book_id: str) -> ReadingPosition | None:
        """Get the last recorded reading position for a book."""
        model = (
            self._session.query(ReadingHistoryModel)
            .filter(ReadingHistoryModel.book_id == book_id)
            .order_by(ReadingHistoryModel.accessed_at.desc())
            .first()
        )
        if model is None:
            return None

        data = json.loads(model.position_data)
        return ReadingPosition(
            page=data.get("page"),
            chapter=data.get("chapter"),
            scroll_offset=data.get("scroll_offset", 0.0),
        )

    def get_history_for_book(self, book_id: str) -> list[ReadingHistory]:
        """Get all reading history entries for a book, most recent first."""
        models = (
            self._session.query(ReadingHistoryModel)
            .filter(ReadingHistoryModel.book_id == book_id)
            .order_by(ReadingHistoryModel.accessed_at.desc())
            .all()
        )
        return [
            ReadingHistory(
                id=m.id,
                book_id=m.book_id,
                position_data=m.position_data,
                accessed_at=m.accessed_at,
            )
            for m in models
        ]

    def get_last_read_time(self, book_id: str) -> datetime | None:
        """Get the most recent access time for a book."""
        model = (
            self._session.query(ReadingHistoryModel)
            .filter(ReadingHistoryModel.book_id == book_id)
            .order_by(ReadingHistoryModel.accessed_at.desc())
            .first()
        )
        if model is None:
            return None
        return model.accessed_at
