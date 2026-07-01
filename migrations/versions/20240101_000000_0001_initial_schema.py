"""Initial schema - create all tables

Revision ID: 0001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables for the AI Ebook Reader platform."""
    # --- Core entity tables ---

    op.create_table(
        "books",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("author", sa.String()),
        sa.Column("publisher", sa.String()),
        sa.Column("language", sa.String()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("file_path", sa.String(), nullable=False, unique=True),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("cover_image", sa.Text()),
        sa.Column("is_favorite", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    op.create_table(
        "collections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("color", sa.String()),
    )

    # --- Association tables (many-to-many) ---

    op.create_table(
        "book_collections",
        sa.Column(
            "book_id",
            sa.String(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            sa.String(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "book_tags",
        sa.Column(
            "book_id",
            sa.String(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # --- Annotations and related ---

    op.create_table(
        "annotations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "book_id",
            sa.String(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("color", sa.String()),
        sa.Column("selected_text", sa.Text()),
        sa.Column("note_content", sa.Text()),
        sa.Column("position_data", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )

    op.create_table(
        "annotation_tags",
        sa.Column(
            "annotation_id",
            sa.String(),
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "annotation_id",
            sa.String(),
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    op.create_table(
        "bookmarks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "book_id",
            sa.String(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String()),
        sa.Column("position_data", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- Reading history ---

    op.create_table(
        "reading_history",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "book_id",
            sa.String(),
            sa.ForeignKey("books.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position_data", sa.Text()),
        sa.Column("accessed_at", sa.DateTime()),
    )

    # --- Vocabulary and spaced repetition ---

    op.create_table(
        "vocabulary_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("word", sa.String(), nullable=False),
        sa.Column("pronunciation", sa.String()),
        sa.Column("part_of_speech", sa.String()),
        sa.Column("definition", sa.Text()),
        sa.Column("example_sentence", sa.Text()),
        sa.Column(
            "book_id", sa.String(), sa.ForeignKey("books.id", ondelete="SET NULL")
        ),
        sa.Column("position_data", sa.Text()),
        sa.Column("mastery_level", sa.String(), default="new"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    op.create_table(
        "vocabulary_tags",
        sa.Column(
            "vocabulary_id",
            sa.String(),
            sa.ForeignKey("vocabulary_entries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.String(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "review_cards",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "vocabulary_id",
            sa.String(),
            sa.ForeignKey("vocabulary_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("card_type", sa.String(), default="flashcard"),
        sa.Column("difficulty", sa.Float(), default=5.0),
        sa.Column("stability", sa.Float(), default=0.4),
        sa.Column("ease_factor", sa.Float(), default=2.5),
        sa.Column("repetitions", sa.Integer(), default=0),
        sa.Column("last_interval", sa.Float(), default=0.0),
        sa.Column("due_date", sa.DateTime(), nullable=False),
        sa.Column("algorithm", sa.String(), default="fsrs"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    op.create_table(
        "review_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "card_id",
            sa.String(),
            sa.ForeignKey("review_cards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(), nullable=False),
        sa.Column("elapsed_days", sa.Float()),
        sa.Column("scheduled_days", sa.Float()),
        sa.Column("review_duration_ms", sa.Float()),
        sa.Column("reviewed_at", sa.DateTime()),
    )

    # --- Knowledge graph ---

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("label", sa.String()),
    )

    op.create_table(
        "knowledge_links",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "source_node_id",
            sa.String(),
            sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.String(),
            sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- Dictionary cache ---

    op.create_table(
        "dict_cache",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("word", sa.String(), nullable=False),
        sa.Column("language", sa.String()),
        sa.Column("source", sa.String()),
        sa.Column("entry_json", sa.Text(), nullable=False),
        sa.Column("cached_at", sa.DateTime()),
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("dict_cache")
    op.drop_table("knowledge_links")
    op.drop_table("knowledge_nodes")
    op.drop_table("review_logs")
    op.drop_table("review_cards")
    op.drop_table("vocabulary_tags")
    op.drop_table("vocabulary_entries")
    op.drop_table("reading_history")
    op.drop_table("bookmarks")
    op.drop_table("comments")
    op.drop_table("annotation_tags")
    op.drop_table("annotations")
    op.drop_table("book_tags")
    op.drop_table("book_collections")
    op.drop_table("tags")
    op.drop_table("collections")
    op.drop_table("books")
