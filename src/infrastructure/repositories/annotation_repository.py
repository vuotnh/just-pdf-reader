"""Annotation repository layer for Annotation, Comment, and Bookmark CRUD operations.

Provides data access for the Annotation System feature, including:
- Annotation CRUD with position, type, color, and content
- Comment threading (append comments to annotations)
- Bookmark CRUD with position and label
- Tag association for annotations
- Cascade delete (comments, tag associations)

Requirements: 5.1–5.8
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.domain.enums import AnnotationType, HighlightColor
from src.domain.models import Annotation, Bookmark, Comment, Tag
from src.infrastructure.database.models import (
    AnnotationModel,
    BookmarkModel,
    CommentModel,
    TagModel,
    annotation_tags,
)


class AnnotationRepository:
    """Repository for Annotation persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Annotation CRUD
    # ------------------------------------------------------------------

    def add(self, annotation: Annotation) -> Annotation:
        """Persist a new annotation to the database."""
        model = AnnotationModel(
            id=annotation.id,
            book_id=annotation.book_id,
            type=annotation.type.value,
            color=annotation.color.value if annotation.color else None,
            selected_text=annotation.selected_text,
            note_content=annotation.note_content,
            position_data=annotation.position_data,
            created_at=annotation.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return annotation

    def get_by_id(self, annotation_id: str) -> Annotation | None:
        """Retrieve an annotation by its ID."""
        model = self._session.get(AnnotationModel, annotation_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_by_book(self, book_id: str) -> list[Annotation]:
        """Retrieve all annotations for a book, ordered chronologically."""
        models = (
            self._session.query(AnnotationModel)
            .filter(AnnotationModel.book_id == book_id)
            .order_by(AnnotationModel.created_at.asc())
            .all()
        )
        return [self._to_domain(m) for m in models]

    def update(self, annotation: Annotation) -> Annotation:
        """Update an existing annotation."""
        model = self._session.get(AnnotationModel, annotation.id)
        if model is None:
            raise ValueError(f"Annotation with id {annotation.id} not found")

        model.type = annotation.type.value
        model.color = annotation.color.value if annotation.color else None
        model.selected_text = annotation.selected_text
        model.note_content = annotation.note_content
        model.position_data = annotation.position_data
        self._session.flush()
        return self._to_domain(model)

    def delete(self, annotation_id: str) -> bool:
        """Delete an annotation by its ID with cascade (comments, tag associations).

        Returns True if deleted, False if not found.
        """
        model = self._session.get(AnnotationModel, annotation_id)
        if model is None:
            return False
        # SQLAlchemy cascade handles comments deletion.
        # Tag associations are removed via cascade on the association table.
        self._session.delete(model)
        self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Comment operations (threading)
    # ------------------------------------------------------------------

    def add_comment(self, annotation_id: str, content: str) -> Comment | None:
        """Append a comment with timestamp to an annotation.

        Returns the created Comment, or None if annotation not found.
        """
        annotation_model = self._session.get(AnnotationModel, annotation_id)
        if annotation_model is None:
            return None

        comment_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        comment_model = CommentModel(
            id=comment_id,
            annotation_id=annotation_id,
            content=content,
            created_at=now,
        )
        self._session.add(comment_model)
        self._session.flush()

        return Comment(
            id=comment_id,
            annotation_id=annotation_id,
            content=content,
            created_at=now,
        )

    def get_comments(self, annotation_id: str) -> list[Comment]:
        """Get all comments for an annotation, ordered chronologically."""
        models = (
            self._session.query(CommentModel)
            .filter(CommentModel.annotation_id == annotation_id)
            .order_by(CommentModel.created_at.asc())
            .all()
        )
        return [
            Comment(
                id=m.id,
                annotation_id=m.annotation_id,
                content=m.content,
                created_at=m.created_at,
            )
            for m in models
        ]

    # ------------------------------------------------------------------
    # Tag operations for annotations
    # ------------------------------------------------------------------

    def add_tag(self, annotation_id: str, tag_name: str) -> bool:
        """Add a tag to an annotation. Creates the tag if it doesn't exist.

        Returns True if the tag was added, False if annotation not found.
        """
        model = self._session.get(AnnotationModel, annotation_id)
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

    def remove_tag(self, annotation_id: str, tag_name: str) -> bool:
        """Remove a tag from an annotation.

        Returns True if removed, False if annotation or tag not found.
        """
        model = self._session.get(AnnotationModel, annotation_id)
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

    def get_tags(self, annotation_id: str) -> list[Tag]:
        """Get all tags associated with an annotation."""
        model = self._session.get(AnnotationModel, annotation_id)
        if model is None:
            return []
        return [Tag(id=t.id, name=t.name, color=t.color) for t in model.tags]

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_domain(self, model: AnnotationModel) -> Annotation:
        """Convert an ORM model to a domain entity."""
        color = HighlightColor(model.color) if model.color else None
        return Annotation(
            id=model.id,
            book_id=model.book_id,
            type=AnnotationType(model.type),
            selected_text=model.selected_text,
            position_data=model.position_data,
            color=color,
            note_content=model.note_content,
            created_at=model.created_at,
        )


class BookmarkRepository:
    """Repository for Bookmark persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bookmark: Bookmark) -> Bookmark:
        """Persist a new bookmark to the database."""
        model = BookmarkModel(
            id=bookmark.id,
            book_id=bookmark.book_id,
            label=bookmark.label,
            position_data=bookmark.position_data,
            created_at=bookmark.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return bookmark

    def get_by_id(self, bookmark_id: str) -> Bookmark | None:
        """Retrieve a bookmark by its ID."""
        model = self._session.get(BookmarkModel, bookmark_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_by_book(self, book_id: str) -> list[Bookmark]:
        """Retrieve all bookmarks for a book, ordered chronologically."""
        models = (
            self._session.query(BookmarkModel)
            .filter(BookmarkModel.book_id == book_id)
            .order_by(BookmarkModel.created_at.asc())
            .all()
        )
        return [self._to_domain(m) for m in models]

    def delete(self, bookmark_id: str) -> bool:
        """Delete a bookmark by its ID. Returns True if deleted."""
        model = self._session.get(BookmarkModel, bookmark_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def _to_domain(self, model: BookmarkModel) -> Bookmark:
        """Convert an ORM model to a domain entity."""
        return Bookmark(
            id=model.id,
            book_id=model.book_id,
            position_data=model.position_data,
            label=model.label,
            created_at=model.created_at,
        )
