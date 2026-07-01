"""Unit tests for the Annotation service layer.

Tests cover:
- Annotation creation with position, type, color, content
- Comment threading (append comment with timestamp)
- Tag association for annotations
- Annotation deletion with cascade
- Bookmark creation and management
- Markdown export for annotations
"""

import json
import uuid

import pytest

from src.domain.enums import AnnotationType, BookFormat, HighlightColor
from src.domain.models import Book
from src.domain.value_objects import TextPosition
from src.application.services.annotation_service import AnnotationService
from src.infrastructure.repositories.annotation_repository import (
    AnnotationRepository,
    BookmarkRepository,
)
from src.infrastructure.repositories.book_repository import BookRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_book(db_session) -> Book:
    """Create and persist a book for testing."""
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


def _make_service(db_session) -> AnnotationService:
    """Create an AnnotationService with real repositories."""
    annotation_repo = AnnotationRepository(db_session)
    bookmark_repo = BookmarkRepository(db_session)
    return AnnotationService(annotation_repo, bookmark_repo)


# ---------------------------------------------------------------------------
# Annotation Creation Tests
# ---------------------------------------------------------------------------


class TestAnnotationCreation:
    """Tests for creating annotations via the service."""

    def test_create_highlight_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        position = TextPosition(page=5, start_offset=10, end_offset=50)
        ann = service.create_annotation(
            book_id=book.id,
            position=position,
            ann_type=AnnotationType.HIGHLIGHT,
            color=HighlightColor.YELLOW,
            content="Highlighted text here",
        )

        assert ann.id is not None
        assert ann.book_id == book.id
        assert ann.type == AnnotationType.HIGHLIGHT
        assert ann.color == HighlightColor.YELLOW
        assert ann.selected_text == "Highlighted text here"
        assert ann.created_at is not None

    def test_create_annotation_stores_position(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        position = TextPosition(page=10, chapter="ch-2", start_offset=100, end_offset=200)
        ann = service.create_annotation(
            book_id=book.id,
            position=position,
            ann_type=AnnotationType.UNDERLINE,
            color=HighlightColor.GREEN,
            content="Underlined text",
        )

        pos_data = json.loads(ann.position_data)
        assert pos_data["page"] == 10
        assert pos_data["chapter"] == "ch-2"
        assert pos_data["start_offset"] == 100
        assert pos_data["end_offset"] == 200

    def test_create_note_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        position = TextPosition(page=3, start_offset=0, end_offset=20)
        ann = service.create_annotation(
            book_id=book.id,
            position=position,
            ann_type=AnnotationType.NOTE,
            content="This is my note",
        )

        assert ann.type == AnnotationType.NOTE
        assert ann.note_content == "This is my note"

    def test_create_annotation_all_colors(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        for color in HighlightColor:
            position = TextPosition(page=1, start_offset=0, end_offset=10)
            ann = service.create_annotation(
                book_id=book.id,
                position=position,
                ann_type=AnnotationType.HIGHLIGHT,
                color=color,
                content=f"Text with {color.value}",
            )
            assert ann.color == color

    def test_get_annotations_for_book(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos1 = TextPosition(page=1, start_offset=0, end_offset=10)
        pos2 = TextPosition(page=2, start_offset=5, end_offset=15)

        service.create_annotation(
            book.id, pos1, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "First"
        )
        service.create_annotation(
            book.id, pos2, AnnotationType.UNDERLINE, HighlightColor.BLUE, "Second"
        )

        results = service.get_annotations(book.id)
        assert len(results) == 2

    def test_get_annotation_by_id(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1, start_offset=0, end_offset=10)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Test"
        )

        result = service.get_annotation(ann.id)
        assert result is not None
        assert result.id == ann.id

    def test_get_nonexistent_annotation_returns_none(self, db_session):
        service = _make_service(db_session)
        assert service.get_annotation("nonexistent") is None


# ---------------------------------------------------------------------------
# Comment Threading Tests
# ---------------------------------------------------------------------------


class TestCommentThreading:
    """Tests for appending comments to annotations."""

    def test_add_comment_to_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        comment = service.add_comment(ann.id, "Great point!")
        assert comment.content == "Great point!"
        assert comment.annotation_id == ann.id
        assert comment.created_at is not None

    def test_add_multiple_comments(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_comment(ann.id, "First thought")
        service.add_comment(ann.id, "Second thought")
        service.add_comment(ann.id, "Third thought")

        comments = service.get_comments(ann.id)
        assert len(comments) == 3
        assert [c.content for c in comments] == [
            "First thought",
            "Second thought",
            "Third thought",
        ]

    def test_add_comment_to_nonexistent_annotation_raises(self, db_session):
        service = _make_service(db_session)
        with pytest.raises(ValueError):
            service.add_comment("nonexistent", "Comment")


# ---------------------------------------------------------------------------
# Tag Association Tests
# ---------------------------------------------------------------------------


class TestTagAssociation:
    """Tests for tag operations on annotations."""

    def test_add_tag_to_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_tag(ann.id, "important")
        tags = service.get_tags(ann.id)
        assert len(tags) == 1
        assert tags[0].name == "important"

    def test_add_multiple_tags(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_tag(ann.id, "important")
        service.add_tag(ann.id, "review-later")
        service.add_tag(ann.id, "chapter-1")

        tags = service.get_tags(ann.id)
        assert len(tags) == 3
        tag_names = {t.name for t in tags}
        assert tag_names == {"important", "review-later", "chapter-1"}

    def test_remove_tag_from_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_tag(ann.id, "important")
        service.remove_tag(ann.id, "important")

        tags = service.get_tags(ann.id)
        assert len(tags) == 0

    def test_add_tag_to_nonexistent_annotation_raises(self, db_session):
        service = _make_service(db_session)
        with pytest.raises(ValueError):
            service.add_tag("nonexistent", "tag")

    def test_remove_tag_nonexistent_raises(self, db_session):
        service = _make_service(db_session)
        with pytest.raises(ValueError):
            service.remove_tag("nonexistent", "tag")


# ---------------------------------------------------------------------------
# Delete with Cascade Tests
# ---------------------------------------------------------------------------


class TestAnnotationDeletion:
    """Tests for annotation deletion with cascade."""

    def test_delete_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.delete_annotation(ann.id)
        assert service.get_annotation(ann.id) is None

    def test_delete_annotation_cascades_comments(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_comment(ann.id, "Comment 1")
        service.add_comment(ann.id, "Comment 2")

        service.delete_annotation(ann.id)
        # After deletion, getting comments for that annotation returns empty
        comments = service.get_comments(ann.id)
        assert comments == []

    def test_delete_annotation_cascades_tags(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Text"
        )

        service.add_tag(ann.id, "important")
        service.add_tag(ann.id, "review")

        service.delete_annotation(ann.id)
        tags = service.get_tags(ann.id)
        assert tags == []

    def test_delete_nonexistent_annotation_raises(self, db_session):
        service = _make_service(db_session)
        with pytest.raises(ValueError):
            service.delete_annotation("nonexistent")


# ---------------------------------------------------------------------------
# Bookmark Tests
# ---------------------------------------------------------------------------


class TestBookmarkOperations:
    """Tests for bookmark creation and management."""

    def test_create_bookmark(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        position = TextPosition(page=42)
        bm = service.create_bookmark(book.id, position, label="Chapter start")

        assert bm.id is not None
        assert bm.book_id == book.id
        assert bm.label == "Chapter start"

    def test_create_bookmark_position_stored(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        position = TextPosition(page=10, chapter="ch-3", start_offset=50, end_offset=100)
        bm = service.create_bookmark(book.id, position)

        pos_data = json.loads(bm.position_data)
        assert pos_data["page"] == 10
        assert pos_data["chapter"] == "ch-3"

    def test_get_bookmarks_for_book(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        service.create_bookmark(book.id, TextPosition(page=1), label="Start")
        service.create_bookmark(book.id, TextPosition(page=50), label="Middle")

        bookmarks = service.get_bookmarks(book.id)
        assert len(bookmarks) == 2

    def test_delete_bookmark(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        bm = service.create_bookmark(book.id, TextPosition(page=1), label="Test")
        service.delete_bookmark(bm.id)

        bookmarks = service.get_bookmarks(book.id)
        assert len(bookmarks) == 0

    def test_delete_nonexistent_bookmark_raises(self, db_session):
        service = _make_service(db_session)
        with pytest.raises(ValueError):
            service.delete_bookmark("nonexistent")


# ---------------------------------------------------------------------------
# Markdown Export Tests
# ---------------------------------------------------------------------------


class TestMarkdownExport:
    """Tests for Markdown export of annotations."""

    def test_export_empty_annotations(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        result = service.export_markdown(book.id)
        assert "No annotations found" in result

    def test_export_single_annotation(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=5)
        service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, "Important text"
        )

        result = service.export_markdown(book.id)
        assert "# Annotations" in result
        assert "Highlight" in result
        assert "yellow" in result
        assert "Important text" in result
        assert "Page 5" in result

    def test_export_includes_tags(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.GREEN, "Tagged text"
        )
        service.add_tag(ann.id, "key-concept")
        service.add_tag(ann.id, "review")

        result = service.export_markdown(book.id)
        assert "key-concept" in result
        assert "review" in result

    def test_export_includes_comments(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=1)
        ann = service.create_annotation(
            book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.BLUE, "Commented text"
        )
        service.add_comment(ann.id, "My first thought")
        service.add_comment(ann.id, "Follow-up thought")

        result = service.export_markdown(book.id)
        assert "My first thought" in result
        assert "Follow-up thought" in result

    def test_export_includes_note_content(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        pos = TextPosition(page=3)
        service.create_annotation(
            book.id, pos, AnnotationType.NOTE, content="This is my detailed note"
        )

        result = service.export_markdown(book.id)
        assert "This is my detailed note" in result

    def test_export_multiple_annotations(self, db_session):
        book = _make_book(db_session)
        service = _make_service(db_session)

        for i in range(3):
            pos = TextPosition(page=i + 1)
            service.create_annotation(
                book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, f"Text {i + 1}"
            )

        result = service.export_markdown(book.id)
        assert "Annotation 1" in result
        assert "Annotation 2" in result
        assert "Annotation 3" in result
        assert "Text 1" in result
        assert "Text 2" in result
        assert "Text 3" in result

    def test_export_contains_all_annotation_blocks(self, db_session):
        """Property 10: Export SHALL contain every annotation."""
        book = _make_book(db_session)
        service = _make_service(db_session)

        annotations_count = 5
        for i in range(annotations_count):
            pos = TextPosition(page=i + 1)
            service.create_annotation(
                book.id, pos, AnnotationType.HIGHLIGHT, HighlightColor.YELLOW, f"Ann {i}"
            )

        result = service.export_markdown(book.id)
        # Count annotation blocks (each starts with "## Annotation N")
        annotation_blocks = result.count("## Annotation")
        assert annotation_blocks == annotations_count
