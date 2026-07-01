"""Unit tests for the Library repository layer.

Tests cover:
- Book CRUD operations
- Sorting by all criteria (title, author, date_added, last_read, file_size)
- Filtering by tag, collection, favorite status
- Tag management
- Collection management
- Reading history recording and last-read position persistence
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domain.enums import BookFormat, SortCriterion
from src.domain.models import Book, Collection, Tag
from src.domain.value_objects import BookFilter, ReadingPosition
from src.infrastructure.repositories.book_repository import (
    BookRepository,
    CollectionRepository,
    ReadingHistoryRepository,
    TagRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_book(
    title: str = "Test Book",
    author: str | None = "Author",
    format: BookFormat = BookFormat.PDF,
    is_favorite: bool = False,
    page_count: int | None = 200,
    created_at: datetime | None = None,
) -> Book:
    """Create a domain Book for testing."""
    return Book(
        id=str(uuid.uuid4()),
        title=title,
        author=author,
        file_path=f"/books/{uuid.uuid4()}.{format.value}",
        file_hash=str(uuid.uuid4()),
        format=format,
        is_favorite=is_favorite,
        page_count=page_count,
        created_at=created_at or datetime.now(UTC),
        updated_at=created_at or datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Book CRUD Tests
# ---------------------------------------------------------------------------


class TestBookCRUD:
    """Tests for basic Book create, read, update, delete operations."""

    def test_add_and_get_book(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book(title="My PDF Book")

        repo.add(book)
        result = repo.get_by_id(book.id)

        assert result is not None
        assert result.id == book.id
        assert result.title == "My PDF Book"
        assert result.format == BookFormat.PDF

    def test_get_nonexistent_book_returns_none(self, db_session):
        repo = BookRepository(db_session)
        assert repo.get_by_id("nonexistent-id") is None

    def test_get_all_books(self, db_session):
        repo = BookRepository(db_session)
        book1 = _make_book(title="Book A")
        book2 = _make_book(title="Book B")

        repo.add(book1)
        repo.add(book2)
        results = repo.get_all()

        assert len(results) == 2
        titles = {b.title for b in results}
        assert titles == {"Book A", "Book B"}

    def test_update_book(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book(title="Original Title")
        repo.add(book)

        book.title = "Updated Title"
        book.author = "New Author"
        repo.update(book)

        result = repo.get_by_id(book.id)
        assert result.title == "Updated Title"
        assert result.author == "New Author"

    def test_update_nonexistent_book_raises(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()

        with pytest.raises(ValueError):
            repo.update(book)

    def test_delete_book(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)

        assert repo.delete(book.id) is True
        assert repo.get_by_id(book.id) is None

    def test_delete_nonexistent_book_returns_false(self, db_session):
        repo = BookRepository(db_session)
        assert repo.delete("nonexistent") is False

    def test_set_favorite(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book(is_favorite=False)
        repo.add(book)

        assert repo.set_favorite(book.id, True) is True

        result = repo.get_by_id(book.id)
        assert result.is_favorite is True

    def test_set_favorite_nonexistent_returns_false(self, db_session):
        repo = BookRepository(db_session)
        assert repo.set_favorite("nonexistent", True) is False

    def test_get_by_file_hash(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)

        result = repo.get_by_file_hash(book.file_hash)
        assert result is not None
        assert result.id == book.id

    def test_get_by_file_hash_not_found(self, db_session):
        repo = BookRepository(db_session)
        assert repo.get_by_file_hash("nonexistent-hash") is None


# ---------------------------------------------------------------------------
# Sorting Tests
# ---------------------------------------------------------------------------


class TestBookSorting:
    """Tests for library sorting by all criteria."""

    def test_sort_by_title(self, db_session):
        repo = BookRepository(db_session)
        repo.add(_make_book(title="Zebra"))
        repo.add(_make_book(title="Apple"))
        repo.add(_make_book(title="Mango"))

        results = repo.get_all(sort_by=SortCriterion.TITLE)
        titles = [b.title for b in results]
        assert titles == ["Apple", "Mango", "Zebra"]

    def test_sort_by_author(self, db_session):
        repo = BookRepository(db_session)
        repo.add(_make_book(title="B1", author="Zoe"))
        repo.add(_make_book(title="B2", author="Alice"))
        repo.add(_make_book(title="B3", author="Mike"))

        results = repo.get_all(sort_by=SortCriterion.AUTHOR)
        authors = [b.author for b in results]
        assert authors == ["Alice", "Mike", "Zoe"]

    def test_sort_by_date_added(self, db_session):
        repo = BookRepository(db_session)
        now = datetime.now(UTC)
        repo.add(_make_book(title="Old", created_at=now - timedelta(days=10)))
        repo.add(_make_book(title="New", created_at=now))
        repo.add(_make_book(title="Mid", created_at=now - timedelta(days=5)))

        results = repo.get_all(sort_by=SortCriterion.DATE_ADDED)
        titles = [b.title for b in results]
        # Most recent first (descending)
        assert titles == ["New", "Mid", "Old"]

    def test_sort_by_file_size(self, db_session):
        repo = BookRepository(db_session)
        repo.add(_make_book(title="Small", page_count=50))
        repo.add(_make_book(title="Big", page_count=500))
        repo.add(_make_book(title="Medium", page_count=200))

        results = repo.get_all(sort_by=SortCriterion.FILE_SIZE)
        titles = [b.title for b in results]
        # Largest first (descending)
        assert titles == ["Big", "Medium", "Small"]

    def test_sort_by_last_read(self, db_session):
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        now = datetime.now(UTC)
        book_old = _make_book(title="Read long ago")
        book_recent = _make_book(title="Read recently")
        book_never = _make_book(title="Never read")

        repo.add(book_old)
        repo.add(book_recent)
        repo.add(book_never)

        # Record reading history
        history_repo.record_open(
            book_old.id, ReadingPosition(page=1)
        )
        history_repo.record_open(
            book_recent.id, ReadingPosition(page=5)
        )

        results = repo.get_all(sort_by=SortCriterion.LAST_READ)
        titles = [b.title for b in results]
        # Most recently read first, never-read last
        assert titles[0] == "Read recently"
        assert titles[-1] == "Never read"


# ---------------------------------------------------------------------------
# Filtering Tests
# ---------------------------------------------------------------------------


class TestBookFiltering:
    """Tests for filtering by tag, collection, and favorite status."""

    def test_filter_by_favorite(self, db_session):
        repo = BookRepository(db_session)
        repo.add(_make_book(title="Fav", is_favorite=True))
        repo.add(_make_book(title="Not Fav", is_favorite=False))

        results = repo.get_all(filter=BookFilter(is_favorite=True))
        assert len(results) == 1
        assert results[0].title == "Fav"

    def test_filter_by_tag(self, db_session):
        repo = BookRepository(db_session)
        book1 = _make_book(title="Tagged")
        book2 = _make_book(title="Untagged")
        repo.add(book1)
        repo.add(book2)

        repo.add_tag(book1.id, "fiction")

        results = repo.get_all(filter=BookFilter(tag="fiction"))
        assert len(results) == 1
        assert results[0].title == "Tagged"

    def test_filter_by_collection(self, db_session):
        repo = BookRepository(db_session)
        coll_repo = CollectionRepository(db_session)

        book1 = _make_book(title="In Collection")
        book2 = _make_book(title="Not In Collection")
        repo.add(book1)
        repo.add(book2)

        collection = coll_repo.create("My Collection")
        repo.add_to_collection(book1.id, collection.id)

        results = repo.get_all(filter=BookFilter(collection_id=collection.id))
        assert len(results) == 1
        assert results[0].title == "In Collection"

    def test_filter_by_format(self, db_session):
        repo = BookRepository(db_session)
        repo.add(_make_book(title="PDF Book", format=BookFormat.PDF))
        repo.add(_make_book(title="EPUB Book", format=BookFormat.EPUB))

        results = repo.get_all(filter=BookFilter(format=BookFormat.EPUB))
        assert len(results) == 1
        assert results[0].title == "EPUB Book"

    def test_combined_filter(self, db_session):
        repo = BookRepository(db_session)
        book1 = _make_book(title="Fav Tagged", is_favorite=True)
        book2 = _make_book(title="Fav Untagged", is_favorite=True)
        book3 = _make_book(title="Not Fav Tagged", is_favorite=False)
        repo.add(book1)
        repo.add(book2)
        repo.add(book3)

        repo.add_tag(book1.id, "sci-fi")
        repo.add_tag(book3.id, "sci-fi")

        results = repo.get_all(filter=BookFilter(is_favorite=True, tag="sci-fi"))
        assert len(results) == 1
        assert results[0].title == "Fav Tagged"


# ---------------------------------------------------------------------------
# Tag Management Tests
# ---------------------------------------------------------------------------


class TestTagOperations:
    """Tests for tag CRUD and book-tag associations."""

    def test_add_tag_to_book(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)

        assert repo.add_tag(book.id, "fiction") is True
        tags = repo.get_tags_for_book(book.id)
        assert len(tags) == 1
        assert tags[0].name == "fiction"

    def test_add_duplicate_tag_is_idempotent(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)

        repo.add_tag(book.id, "fiction")
        repo.add_tag(book.id, "fiction")

        tags = repo.get_tags_for_book(book.id)
        assert len(tags) == 1

    def test_add_tag_to_nonexistent_book(self, db_session):
        repo = BookRepository(db_session)
        assert repo.add_tag("nonexistent", "tag") is False

    def test_remove_tag_from_book(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)
        repo.add_tag(book.id, "fiction")

        assert repo.remove_tag(book.id, "fiction") is True
        tags = repo.get_tags_for_book(book.id)
        assert len(tags) == 0

    def test_remove_nonexistent_tag(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)
        assert repo.remove_tag(book.id, "nonexistent") is False

    def test_tag_repository_crud(self, db_session):
        tag_repo = TagRepository(db_session)
        tag = tag_repo.create("science", color="#0000FF")

        assert tag.name == "science"
        assert tag.color == "#0000FF"

        result = tag_repo.get_by_id(tag.id)
        assert result is not None
        assert result.name == "science"

        result = tag_repo.get_by_name("science")
        assert result is not None
        assert result.id == tag.id

        all_tags = tag_repo.get_all()
        assert len(all_tags) == 1

        assert tag_repo.delete(tag.id) is True
        assert tag_repo.get_by_id(tag.id) is None


# ---------------------------------------------------------------------------
# Collection Tests
# ---------------------------------------------------------------------------


class TestCollectionOperations:
    """Tests for collection CRUD and book-collection associations."""

    def test_create_collection(self, db_session):
        coll_repo = CollectionRepository(db_session)
        coll = coll_repo.create("My Collection", description="Some books")

        assert coll.name == "My Collection"
        assert coll.description == "Some books"
        assert coll.id is not None

    def test_get_collection_by_id(self, db_session):
        coll_repo = CollectionRepository(db_session)
        coll = coll_repo.create("Test")

        result = coll_repo.get_by_id(coll.id)
        assert result is not None
        assert result.name == "Test"

    def test_get_all_collections(self, db_session):
        coll_repo = CollectionRepository(db_session)
        coll_repo.create("Alpha")
        coll_repo.create("Beta")

        results = coll_repo.get_all()
        assert len(results) == 2
        # Sorted by name
        assert results[0].name == "Alpha"
        assert results[1].name == "Beta"

    def test_delete_collection(self, db_session):
        coll_repo = CollectionRepository(db_session)
        coll = coll_repo.create("To Delete")

        assert coll_repo.delete(coll.id) is True
        assert coll_repo.get_by_id(coll.id) is None

    def test_add_book_to_collection(self, db_session):
        repo = BookRepository(db_session)
        coll_repo = CollectionRepository(db_session)

        book = _make_book(title="Collected Book")
        repo.add(book)
        coll = coll_repo.create("Reading List")

        assert repo.add_to_collection(book.id, coll.id) is True

        books = coll_repo.get_books_in_collection(coll.id)
        assert len(books) == 1
        assert books[0].title == "Collected Book"

    def test_remove_book_from_collection(self, db_session):
        repo = BookRepository(db_session)
        coll_repo = CollectionRepository(db_session)

        book = _make_book()
        repo.add(book)
        coll = coll_repo.create("Temp")
        repo.add_to_collection(book.id, coll.id)

        assert repo.remove_from_collection(book.id, coll.id) is True
        books = coll_repo.get_books_in_collection(coll.id)
        assert len(books) == 0

    def test_add_to_nonexistent_collection(self, db_session):
        repo = BookRepository(db_session)
        book = _make_book()
        repo.add(book)

        assert repo.add_to_collection(book.id, "nonexistent") is False

    def test_add_nonexistent_book_to_collection(self, db_session):
        repo = BookRepository(db_session)
        coll_repo = CollectionRepository(db_session)
        coll = coll_repo.create("Empty")

        assert repo.add_to_collection("nonexistent", coll.id) is False


# ---------------------------------------------------------------------------
# Reading History Tests
# ---------------------------------------------------------------------------


class TestReadingHistory:
    """Tests for reading history recording and last-read position persistence."""

    def test_record_open(self, db_session):
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book()
        repo.add(book)

        position = ReadingPosition(page=42, scroll_offset=0.5)
        history = history_repo.record_open(book.id, position)

        assert history.book_id == book.id
        assert history.id is not None

    def test_get_last_position(self, db_session):
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book()
        repo.add(book)

        history_repo.record_open(book.id, ReadingPosition(page=1))
        history_repo.record_open(book.id, ReadingPosition(page=10, scroll_offset=0.3))

        last_pos = history_repo.get_last_position(book.id)
        assert last_pos is not None
        assert last_pos.page == 10
        assert last_pos.scroll_offset == 0.3

    def test_get_last_position_no_history(self, db_session):
        history_repo = ReadingHistoryRepository(db_session)
        assert history_repo.get_last_position("nonexistent") is None

    def test_get_history_for_book(self, db_session):
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book()
        repo.add(book)

        history_repo.record_open(book.id, ReadingPosition(page=1))
        history_repo.record_open(book.id, ReadingPosition(page=5))
        history_repo.record_open(book.id, ReadingPosition(page=10))

        history = history_repo.get_history_for_book(book.id)
        assert len(history) == 3

    def test_reading_position_round_trip_pdf(self, db_session):
        """Property 6: Reading position round-trip for PDF (page-based)."""
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book(format=BookFormat.PDF)
        repo.add(book)

        original = ReadingPosition(page=99, scroll_offset=0.75)
        history_repo.record_open(book.id, original)

        restored = history_repo.get_last_position(book.id)
        assert restored == original

    def test_reading_position_round_trip_epub(self, db_session):
        """Property 6: Reading position round-trip for EPUB (chapter-based)."""
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book(format=BookFormat.EPUB)
        repo.add(book)

        original = ReadingPosition(chapter="chapter-3", scroll_offset=0.5)
        history_repo.record_open(book.id, original)

        restored = history_repo.get_last_position(book.id)
        assert restored == original

    def test_get_last_read_time(self, db_session):
        repo = BookRepository(db_session)
        history_repo = ReadingHistoryRepository(db_session)

        book = _make_book()
        repo.add(book)

        assert history_repo.get_last_read_time(book.id) is None

        history_repo.record_open(book.id, ReadingPosition(page=1))
        last_time = history_repo.get_last_read_time(book.id)
        assert last_time is not None
        assert isinstance(last_time, datetime)
