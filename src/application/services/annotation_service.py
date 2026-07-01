"""Annotation service implementing the IAnnotationService protocol.

Orchestrates annotation management including creation, comment threading,
tag association, deletion with cascade, and Markdown export.

Requirements: 5.1–5.8
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from src.domain.enums import AnnotationType, HighlightColor
from src.domain.models import Annotation, Bookmark, Comment
from src.domain.value_objects import TextPosition
from src.infrastructure.repositories.annotation_repository import (
    AnnotationRepository,
    BookmarkRepository,
)


class AnnotationService:
    """Application-layer service for annotation management.

    Implements the IAnnotationService protocol from the design document,
    coordinating repositories to handle:
    - Annotation creation with position, type, color, and content
    - Comment threading (append comments with timestamp)
    - Tag association for annotations
    - Annotation deletion with cascade (comments, tag associations)
    - Markdown export for all annotations of a book
    """

    def __init__(
        self,
        annotation_repo: AnnotationRepository,
        bookmark_repo: BookmarkRepository,
    ) -> None:
        self._annotation_repo = annotation_repo
        self._bookmark_repo = bookmark_repo

    # ------------------------------------------------------------------
    # Annotation operations
    # ------------------------------------------------------------------

    def create_annotation(
        self,
        book_id: str,
        position: TextPosition,
        ann_type: AnnotationType,
        color: HighlightColor | None = None,
        content: str | None = None,
    ) -> Annotation:
        """Create a new annotation with exact text position, book reference, timestamp, type, color.

        Args:
            book_id: The ID of the book being annotated.
            position: The text position (page/chapter + offsets).
            ann_type: The type of annotation (highlight, underline, note, comment).
            color: Optional highlight color.
            content: The selected text or note content.

        Returns:
            The created Annotation domain object.
        """
        annotation_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Serialize position to JSON
        position_data = json.dumps({
            "page": position.page,
            "chapter": position.chapter,
            "start_offset": position.start_offset,
            "end_offset": position.end_offset,
        })

        # For note/comment types, content goes to note_content
        # For highlight/underline, content is the selected text
        if ann_type in (AnnotationType.NOTE, AnnotationType.COMMENT):
            selected_text = content or ""
            note_content = content
        else:
            selected_text = content or ""
            note_content = None

        annotation = Annotation(
            id=annotation_id,
            book_id=book_id,
            type=ann_type,
            selected_text=selected_text,
            position_data=position_data,
            color=color,
            note_content=note_content,
            created_at=now,
        )

        return self._annotation_repo.add(annotation)

    def get_annotations(self, book_id: str) -> list[Annotation]:
        """Get all annotations for a book in chronological order.

        Args:
            book_id: The ID of the book.

        Returns:
            List of Annotation domain objects ordered by creation time.
        """
        return self._annotation_repo.get_by_book(book_id)

    def get_annotation(self, annotation_id: str) -> Annotation | None:
        """Get a single annotation by ID.

        Args:
            annotation_id: The annotation's unique ID.

        Returns:
            The Annotation domain object, or None if not found.
        """
        return self._annotation_repo.get_by_id(annotation_id)

    # ------------------------------------------------------------------
    # Comment operations (threading)
    # ------------------------------------------------------------------

    def add_comment(self, annotation_id: str, content: str) -> Comment:
        """Append a comment with timestamp to an annotation.

        Args:
            annotation_id: The ID of the annotation to comment on.
            content: The comment text.

        Returns:
            The created Comment domain object.

        Raises:
            ValueError: If the annotation does not exist.
        """
        comment = self._annotation_repo.add_comment(annotation_id, content)
        if comment is None:
            raise ValueError(f"Annotation '{annotation_id}' not found.")
        return comment

    def get_comments(self, annotation_id: str) -> list[Comment]:
        """Get all comments for an annotation in chronological order.

        Args:
            annotation_id: The ID of the annotation.

        Returns:
            List of Comment domain objects.
        """
        return self._annotation_repo.get_comments(annotation_id)

    # ------------------------------------------------------------------
    # Tag operations
    # ------------------------------------------------------------------

    def add_tag(self, annotation_id: str, tag: str) -> None:
        """Associate a tag with an annotation.

        Args:
            annotation_id: The ID of the annotation.
            tag: The tag name to associate.

        Raises:
            ValueError: If the annotation does not exist.
        """
        success = self._annotation_repo.add_tag(annotation_id, tag)
        if not success:
            raise ValueError(f"Annotation '{annotation_id}' not found.")

    def remove_tag(self, annotation_id: str, tag: str) -> None:
        """Remove a tag from an annotation.

        Args:
            annotation_id: The ID of the annotation.
            tag: The tag name to remove.

        Raises:
            ValueError: If the annotation or tag association not found.
        """
        success = self._annotation_repo.remove_tag(annotation_id, tag)
        if not success:
            raise ValueError(
                f"Failed to remove tag '{tag}' from annotation '{annotation_id}'."
            )

    def get_tags(self, annotation_id: str) -> list:
        """Get all tags associated with an annotation.

        Args:
            annotation_id: The ID of the annotation.

        Returns:
            List of Tag domain objects.
        """
        return self._annotation_repo.get_tags(annotation_id)

    # ------------------------------------------------------------------
    # Delete operations
    # ------------------------------------------------------------------

    def delete_annotation(self, annotation_id: str) -> None:
        """Delete an annotation with cascade (comments, tag associations).

        Args:
            annotation_id: The ID of the annotation to delete.

        Raises:
            ValueError: If the annotation does not exist.
        """
        success = self._annotation_repo.delete(annotation_id)
        if not success:
            raise ValueError(f"Annotation '{annotation_id}' not found.")

    # ------------------------------------------------------------------
    # Bookmark operations
    # ------------------------------------------------------------------

    def create_bookmark(
        self,
        book_id: str,
        position: TextPosition,
        label: str | None = None,
    ) -> Bookmark:
        """Create a new bookmark at a specific position.

        Args:
            book_id: The ID of the book.
            position: The text position (page/chapter).
            label: Optional descriptive label.

        Returns:
            The created Bookmark domain object.
        """
        bookmark_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        position_data = json.dumps({
            "page": position.page,
            "chapter": position.chapter,
            "start_offset": position.start_offset,
            "end_offset": position.end_offset,
        })

        bookmark = Bookmark(
            id=bookmark_id,
            book_id=book_id,
            position_data=position_data,
            label=label,
            created_at=now,
        )

        return self._bookmark_repo.add(bookmark)

    def get_bookmarks(self, book_id: str) -> list[Bookmark]:
        """Get all bookmarks for a book in chronological order.

        Args:
            book_id: The ID of the book.

        Returns:
            List of Bookmark domain objects.
        """
        return self._bookmark_repo.get_by_book(book_id)

    def delete_bookmark(self, bookmark_id: str) -> None:
        """Delete a bookmark.

        Args:
            bookmark_id: The ID of the bookmark to delete.

        Raises:
            ValueError: If the bookmark does not exist.
        """
        success = self._bookmark_repo.delete(bookmark_id)
        if not success:
            raise ValueError(f"Bookmark '{bookmark_id}' not found.")

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def export_markdown(self, book_id: str) -> str:
        """Generate a Markdown file containing all annotations for a book.

        The export includes each annotation's selected text, note content,
        tags, comments, and source location (position data).

        Args:
            book_id: The ID of the book to export annotations for.

        Returns:
            A Markdown-formatted string with all annotations.
        """
        annotations = self._annotation_repo.get_by_book(book_id)

        if not annotations:
            return f"# Annotations\n\nNo annotations found for this book.\n"

        lines: list[str] = []
        lines.append("# Annotations\n")

        for i, ann in enumerate(annotations, start=1):
            lines.append(f"## Annotation {i}\n")

            # Type and color
            type_label = ann.type.value.capitalize()
            if ann.color:
                lines.append(f"**Type:** {type_label} ({ann.color.value})\n")
            else:
                lines.append(f"**Type:** {type_label}\n")

            # Position
            position = json.loads(ann.position_data)
            position_parts = []
            if position.get("page") is not None:
                position_parts.append(f"Page {position['page']}")
            if position.get("chapter"):
                position_parts.append(f"Chapter: {position['chapter']}")
            if position_parts:
                lines.append(f"**Location:** {', '.join(position_parts)}\n")

            # Selected text
            if ann.selected_text:
                lines.append(f"**Text:** > {ann.selected_text}\n")

            # Note content
            if ann.note_content:
                lines.append(f"**Note:** {ann.note_content}\n")

            # Tags
            tags = self._annotation_repo.get_tags(ann.id)
            if tags:
                tag_names = [t.name for t in tags]
                lines.append(f"**Tags:** {', '.join(tag_names)}\n")

            # Comments
            comments = self._annotation_repo.get_comments(ann.id)
            if comments:
                lines.append("**Comments:**\n")
                for comment in comments:
                    timestamp = comment.created_at.strftime("%Y-%m-%d %H:%M")
                    lines.append(f"- [{timestamp}] {comment.content}\n")

            # Timestamp
            lines.append(
                f"**Created:** {ann.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            lines.append("---\n")

        return "\n".join(lines)
