"""Unit tests for the Annotation repository layer.

Tests cover:
- Annotation CRUD operations
- Comment threading (append comments to annotations)
- Bookmark CRUD operations
- Tag association for annotations
- Cascade delete (comments, tag associations)
"""

import json
import uuid
from datetime import UTC, datetime

import pytest

from src.domain.enums import AnnotationType, BookFormat, HighlightColor
from src.domain.models import Annotation, Book, Bookmark
from src.infrastructure.repositories.annotation_repository import (
    AnnotationRepository,
    BookmarkRepository,
)
from src.infrastructure.repositories.book_repository import BookRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_book(db_session) -> Book:
    """Create and persist a book for testing annotations."""
    book = Book(
        id=str(uuid.uuid4()),
        title="Test Book",
        author="Author",
        file_path=f"/books/{uuid.uuid4()}.pdf",
        file_hash=str(uuid.uuid4()),
        format=BookFormat.PDF,
    )
    repo = BookRepository(db_session)
    repo.add(book)
    return book


def _make_annotation(
    book_id: str,
    ann_type: AnnotationType = AnnotationType.HIGHLIGHT,
    color: HighlightColor = HighlightColor.YELLOW,
    selected_text: str = "Some highlighted text",
    note_content: str | None = None,
    page: int = 1,
) -> Annotation:
    """Create a domain Annotation for testing."""
    position_data = json.dumps({
        "page": page,
        "chapter": None,
        "start_offset": 10,
        "end_offset": 50,
    })
    return Annotation(
        id=str(uuid.uuid4()),
        book_id=book_id,
        type=ann_type,
        selected_text=selected_text,
        position_data=position_data,
        color=color,
        note_content=note_content,
        created_at=datetime.now(UTC),
    )


def _make_bookmark(
    book_id: str,
    label: str | None = "Important page",
    page: int = 5,
) -> Bookmark:
    """Create a domain Bookmark for testing."""
    position_data = json.dumps({
        "page": page,
        "chapter": None,
        "start_offset": 0,
        "end_offset": 0,
    })
    return Bookmark(
        id=str(uuid.uuid4()),
        book_id=book_id,
        position_data=position_data,
        label=label,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Annotation CRUD Tests
# ---------------------------------------------------------------------------


class TestAnnotationCRUD:
    """Tests for basic Annotation create, read, update, delete operations."""

    def test_add_and_get_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)

        repo.add(ann)
        result = repo.get_by_id(ann.id)

        assert result is not None
        assert result.id == ann.id
        assert result.book_id == book.id
        assert result.type == AnnotationType.HIGHLIGHT
        assert result.color == HighlightColor.YELLOW
        assert result.selected_text == "Some highlighted text"

    def test_get_nonexistent_annotation_returns_none(self, db_session):
        repo = AnnotationRepository(db_session)
        assert repo.get_by_id("nonexistent-id") is None

    def test_get_annotations_by_book(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)

        ann1 = _make_annotation(book.id, selected_text="First")
        ann2 = _make_annotation(book.id, selected_text="Second")
        repo.add(ann1)
        repo.add(ann2)

        results = repo.get_by_book(book.id)
        assert len(results) == 2
        texts = {a.selected_text for a in results}
        assert texts == {"First", "Second"}

    def test_get_annotations_for_nonexistent_book(self, db_session):
        repo = AnnotationRepository(db_session)
        results = repo.get_by_book("nonexistent")
        assert results == []

    def test_update_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        ann.note_content = "Updated note"
        ann.color = HighlightColor.BLUE
        repo.update(ann)

        result = repo.get_by_id(ann.id)
        assert result.note_content == "Updated note"
        assert result.color == HighlightColor.BLUE

    def test_update_nonexistent_annotation_raises(self, db_session):
        repo = AnnotationRepository(db_session)
        ann = _make_annotation("some-book-id")

        with pytest.raises(ValueError):
            repo.update(ann)

    def test_delete_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        assert repo.delete(ann.id) is True
        assert repo.get_by_id(ann.id) is None

    def test_delete_nonexistent_annotation_returns_false(self, db_session):
        repo = AnnotationRepository(db_session)
        assert repo.delete("nonexistent") is False

    def test_annotation_types(self, db_session):
        """Test all annotation types are supported."""
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)

        for ann_type in AnnotationType:
            ann = _make_annotation(book.id, ann_type=ann_type)
            repo.add(ann)
            result = repo.get_by_id(ann.id)
            assert result.type == ann_type

    def test_annotation_colors(self, db_session):
        """Test all highlight colors are supported."""
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)

        for color in HighlightColor:
            ann = _make_annotation(book.id, color=color)
            repo.add(ann)
            result = repo.get_by_id(ann.id)
            assert result.color == color

    def test_annotation_without_color(self, db_session):
        """Test annotation can have no color (e.g., note type)."""
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)

        ann = _make_annotation(book.id, ann_type=AnnotationType.NOTE, color=None)
        ann.color = None
        repo.add(ann)

        result = repo.get_by_id(ann.id)
        assert result.color is None


# ---------------------------------------------------------------------------
# Comment Threading Tests
# ---------------------------------------------------------------------------


class TestCommentThreading:
    """Tests for comment operations on annotations."""

    def test_add_comment_to_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        comment = repo.add_comment(ann.id, "Great insight!")
        assert comment is not None
        assert comment.annotation_id == ann.id
        assert comment.content == "Great insight!"
        assert comment.created_at is not None

    def test_add_comment_to_nonexistent_annotation_returns_none(self, db_session):
        repo = AnnotationRepository(db_session)
        result = repo.add_comment("nonexistent", "test")
        assert result is None

    def test_multiple_comments_on_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        repo.add_comment(ann.id, "First comment")
        repo.add_comment(ann.id, "Second comment")
        repo.add_comment(ann.id, "Third comment")

        comments = repo.get_comments(ann.id)
        assert len(comments) == 3
        contents = [c.content for c in comments]
        assert contents == ["First comment", "Second comment", "Third comment"]

    def test_comments_have_timestamps(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        comment = repo.add_comment(ann.id, "Timestamped comment")
        assert comment.created_at is not None
        assert isinstance(comment.created_at, datetime)

    def test_get_comments_empty(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        comments = repo.get_comments(ann.id)
        assert comments == []


# ---------------------------------------------------------------------------
# Cascade Delete Tests
# ---------------------------------------------------------------------------


class TestCascadeDelete:
    """Tests for annotation deletion cascading to comments and tags."""

    def test_delete_annotation_cascades_to_comments(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        repo.add_comment(ann.id, "Comment 1")
        repo.add_comment(ann.id, "Comment 2")

        # Verify comments exist
        assert len(repo.get_comments(ann.id)) == 2

        # Delete annotation
        repo.delete(ann.id)

        # Comments should be gone
        assert repo.get_comments(ann.id) == []

    def test_delete_annotation_cascades_to_tag_associations(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        repo.add_tag(ann.id, "important")
        repo.add_tag(ann.id, "review")

        # Verify tags exist
        assert len(repo.get_tags(ann.id)) == 2

        # Delete annotation
        repo.delete(ann.id)

        # Tag associations should be gone (but tags themselves remain)
        assert repo.get_tags(ann.id) == []


# ---------------------------------------------------------------------------
# Tag Operations Tests
# ---------------------------------------------------------------------------


class TestAnnotationTags:
    """Tests for tag association with annotations."""

    def test_add_tag_to_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        assert repo.add_tag(ann.id, "important") is True
        tags = repo.get_tags(ann.id)
        assert len(tags) == 1
        assert tags[0].name == "important"

    def test_add_duplicate_tag_is_idempotent(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        repo.add_tag(ann.id, "important")
        repo.add_tag(ann.id, "important")

        tags = repo.get_tags(ann.id)
        assert len(tags) == 1

    def test_add_tag_to_nonexistent_annotation(self, db_session):
        repo = AnnotationRepository(db_session)
        assert repo.add_tag("nonexistent", "tag") is False

    def test_remove_tag_from_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)
        repo.add_tag(ann.id, "important")

        assert repo.remove_tag(ann.id, "important") is True
        tags = repo.get_tags(ann.id)
        assert len(tags) == 0

    def test_remove_nonexistent_tag(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        assert repo.remove_tag(ann.id, "nonexistent") is False

    def test_multiple_tags_on_annotation(self, db_session):
        book = _make_book(db_session)
        repo = AnnotationRepository(db_session)
        ann = _make_annotation(book.id)
        repo.add(ann)

        repo.add_tag(ann.id, "important")
        repo.add_tag(ann.id, "review")
        repo.add_tag(ann.id, "chapter-1")

        tags = repo.get_tags(ann.id)
        assert len(tags) == 3
        tag_names = {t.name for t in tags}
        assert tag_names == {"important", "review", "chapter-1"}

    def test_get_tags_for_nonexistent_annotation(self, db_session):
        repo = AnnotationRepository(db_session)
        assert repo.get_tags("nonexistent") == []


# ---------------------------------------------------------------------------
# Bookmark CRUD Tests
# ---------------------------------------------------------------------------


class TestBookmarkCRUD:
    """Tests for Bookmark create, read, delete operations."""

    def test_add_and_get_bookmark(self, db_session):
        book = _make_book(db_session)
        repo = BookmarkRepository(db_session)
        bm = _make_bookmark(book.id)

        repo.add(bm)
        result = repo.get_by_id(bm.id)

        assert result is not None
        assert result.id == bm.id
        assert result.book_id == book.id
        assert result.label == "Important page"

    def test_get_nonexistent_bookmark_returns_none(self, db_session):
        repo = BookmarkRepository(db_session)
        assert repo.get_by_id("nonexistent") is None

    def test_get_bookmarks_by_book(self, db_session):
        book = _make_book(db_session)
        repo = BookmarkRepository(db_session)

        bm1 = _make_bookmark(book.id, label="Page 1", page=1)
        bm2 = _make_bookmark(book.id, label="Page 10", page=10)
        repo.add(bm1)
        repo.add(bm2)

        results = repo.get_by_book(book.id)
        assert len(results) == 2
        labels = {b.label for b in results}
        assert labels == {"Page 1", "Page 10"}

    def test_delete_bookmark(self, db_session):
        book = _make_book(db_session)
        repo = BookmarkRepository(db_session)
        bm = _make_bookmark(book.id)
        repo.add(bm)

        assert repo.delete(bm.id) is True
        assert repo.get_by_id(bm.id) is None

    def test_delete_nonexistent_bookmark_returns_false(self, db_session):
        repo = BookmarkRepository(db_session)
        assert repo.delete("nonexistent") is False

    def test_bookmark_without_label(self, db_session):
        book = _make_book(db_session)
        repo = BookmarkRepository(db_session)
        bm = _make_bookmark(book.id, label=None)
        repo.add(bm)

        result = repo.get_by_id(bm.id)
        assert result.label is None

    def test_bookmark_position_data_preserved(self, db_session):
        book = _make_book(db_session)
        repo = BookmarkRepository(db_session)

        position_data = json.dumps({
            "page": 42,
            "chapter": "chapter-3",
            "start_offset": 100,
            "end_offset": 200,
        })
        bm = Bookmark(
            id=str(uuid.uuid4()),
            book_id=book.id,
            position_data=position_data,
            label="Complex position",
            created_at=datetime.now(UTC),
        )
        repo.add(bm)

        result = repo.get_by_id(bm.id)
        assert result.position_data == position_data
        parsed = json.loads(result.position_data)
        assert parsed["page"] == 42
        assert parsed["chapter"] == "chapter-3"
