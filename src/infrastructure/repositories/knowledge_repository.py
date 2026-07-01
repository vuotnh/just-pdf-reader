"""Knowledge Graph repository layer for KnowledgeNode and KnowledgeLink CRUD operations.

Provides data access for the Knowledge Graph feature, including:
- KnowledgeNode CRUD (create, read, update, delete)
- KnowledgeLink CRUD with bidirectional querying
- Filtering nodes and links by entity type, tag, or book
- Querying node connections (neighbors)

Requirements: 9.1–9.5
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.domain.models import KnowledgeLink, KnowledgeNode
from src.infrastructure.database.models import (
    AnnotationModel,
    BookModel,
    KnowledgeLinkModel,
    KnowledgeNodeModel,
    TagModel,
    VocabularyEntryModel,
    book_tags,
    annotation_tags,
    vocabulary_tags,
)


class KnowledgeNodeRepository:
    """Repository for KnowledgeNode persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def add(self, node: KnowledgeNode) -> KnowledgeNode:
        """Persist a new knowledge node to the database."""
        model = KnowledgeNodeModel(
            id=node.id,
            entity_type=node.entity_type,
            entity_id=node.entity_id,
            label=node.label,
        )
        self._session.add(model)
        self._session.flush()
        return node

    def get_by_id(self, node_id: str) -> KnowledgeNode | None:
        """Retrieve a knowledge node by its ID."""
        model = self._session.get(KnowledgeNodeModel, node_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_by_entity(self, entity_type: str, entity_id: str) -> KnowledgeNode | None:
        """Retrieve a knowledge node by its entity type and entity ID."""
        model = (
            self._session.query(KnowledgeNodeModel)
            .filter(
                KnowledgeNodeModel.entity_type == entity_type,
                KnowledgeNodeModel.entity_id == entity_id,
            )
            .first()
        )
        if model is None:
            return None
        return self._to_domain(model)

    def get_all(self, entity_types: list[str] | None = None) -> list[KnowledgeNode]:
        """Retrieve all knowledge nodes, optionally filtered by entity type.

        Args:
            entity_types: Optional list of entity types to filter by
                         (e.g., ["book", "annotation"]).

        Returns:
            List of KnowledgeNode domain objects.
        """
        query = self._session.query(KnowledgeNodeModel)

        if entity_types:
            query = query.filter(KnowledgeNodeModel.entity_type.in_(entity_types))

        return [self._to_domain(m) for m in query.all()]

    def get_nodes_for_book(self, book_id: str) -> list[KnowledgeNode]:
        """Get all nodes related to a specific book.

        Returns the book node itself plus nodes for annotations and vocabulary
        entries that belong to the book.
        """
        # Get the book node
        book_node_model = (
            self._session.query(KnowledgeNodeModel)
            .filter(
                KnowledgeNodeModel.entity_type == "book",
                KnowledgeNodeModel.entity_id == book_id,
            )
            .first()
        )

        # Get annotation entity IDs for this book
        annotation_ids = [
            a.id
            for a in self._session.query(AnnotationModel.id)
            .filter(AnnotationModel.book_id == book_id)
            .all()
        ]

        # Get vocabulary entity IDs for this book
        vocab_ids = [
            v.id
            for v in self._session.query(VocabularyEntryModel.id)
            .filter(VocabularyEntryModel.book_id == book_id)
            .all()
        ]

        # Query nodes matching these entities
        entity_filters = []
        if book_node_model:
            entity_filters.append(KnowledgeNodeModel.id == book_node_model.id)
        if annotation_ids:
            entity_filters.append(
                (KnowledgeNodeModel.entity_type == "annotation")
                & (KnowledgeNodeModel.entity_id.in_(annotation_ids))
            )
        if vocab_ids:
            entity_filters.append(
                (KnowledgeNodeModel.entity_type == "vocabulary")
                & (KnowledgeNodeModel.entity_id.in_(vocab_ids))
            )

        if not entity_filters:
            return []

        models = (
            self._session.query(KnowledgeNodeModel)
            .filter(or_(*entity_filters))
            .all()
        )
        return [self._to_domain(m) for m in models]

    def get_nodes_for_tag(self, tag_name: str) -> list[KnowledgeNode]:
        """Get all nodes related to a specific tag.

        Returns nodes for books, annotations, and vocabulary entries
        that are tagged with the given tag name.
        """
        # Find the tag
        tag_model = (
            self._session.query(TagModel)
            .filter(TagModel.name == tag_name)
            .first()
        )
        if tag_model is None:
            return []

        # Get entity IDs associated with this tag
        book_ids = [
            b.id
            for b in self._session.query(BookModel.id)
            .join(book_tags)
            .filter(book_tags.c.tag_id == tag_model.id)
            .all()
        ]
        annotation_ids = [
            a.id
            for a in self._session.query(AnnotationModel.id)
            .join(annotation_tags)
            .filter(annotation_tags.c.tag_id == tag_model.id)
            .all()
        ]
        vocab_ids = [
            v.id
            for v in self._session.query(VocabularyEntryModel.id)
            .join(vocabulary_tags)
            .filter(vocabulary_tags.c.tag_id == tag_model.id)
            .all()
        ]

        # Build filter for matching nodes
        entity_filters = []
        if book_ids:
            entity_filters.append(
                (KnowledgeNodeModel.entity_type == "book")
                & (KnowledgeNodeModel.entity_id.in_(book_ids))
            )
        if annotation_ids:
            entity_filters.append(
                (KnowledgeNodeModel.entity_type == "annotation")
                & (KnowledgeNodeModel.entity_id.in_(annotation_ids))
            )
        if vocab_ids:
            entity_filters.append(
                (KnowledgeNodeModel.entity_type == "vocabulary")
                & (KnowledgeNodeModel.entity_id.in_(vocab_ids))
            )

        if not entity_filters:
            return []

        models = (
            self._session.query(KnowledgeNodeModel)
            .filter(or_(*entity_filters))
            .all()
        )
        return [self._to_domain(m) for m in models]

    def update(self, node: KnowledgeNode) -> KnowledgeNode:
        """Update an existing knowledge node."""
        model = self._session.get(KnowledgeNodeModel, node.id)
        if model is None:
            raise ValueError(f"KnowledgeNode with id {node.id} not found")

        model.entity_type = node.entity_type
        model.entity_id = node.entity_id
        model.label = node.label
        self._session.flush()
        return self._to_domain(model)

    def delete(self, node_id: str) -> bool:
        """Delete a knowledge node by its ID (cascades to links).

        Returns True if deleted, False if not found.
        """
        model = self._session.get(KnowledgeNodeModel, node_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_domain(self, model: KnowledgeNodeModel) -> KnowledgeNode:
        """Convert an ORM model to a domain entity."""
        return KnowledgeNode(
            id=model.id,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            label=model.label,
        )


class KnowledgeLinkRepository:
    """Repository for KnowledgeLink persistence operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Link CRUD
    # ------------------------------------------------------------------

    def add(self, link: KnowledgeLink) -> KnowledgeLink:
        """Persist a new knowledge link to the database."""
        model = KnowledgeLinkModel(
            id=link.id,
            source_node_id=link.source_node_id,
            target_node_id=link.target_node_id,
            link_type=link.link_type,
            created_at=link.created_at,
        )
        self._session.add(model)
        self._session.flush()
        return link

    def get_by_id(self, link_id: str) -> KnowledgeLink | None:
        """Retrieve a knowledge link by its ID."""
        model = self._session.get(KnowledgeLinkModel, link_id)
        if model is None:
            return None
        return self._to_domain(model)

    def get_all(self) -> list[KnowledgeLink]:
        """Retrieve all knowledge links."""
        models = self._session.query(KnowledgeLinkModel).all()
        return [self._to_domain(m) for m in models]

    def get_links_for_node(self, node_id: str) -> list[KnowledgeLink]:
        """Get all links where the node is either source or target (bidirectional).

        Args:
            node_id: The node ID to find connections for.

        Returns:
            List of KnowledgeLink domain objects.
        """
        models = (
            self._session.query(KnowledgeLinkModel)
            .filter(
                or_(
                    KnowledgeLinkModel.source_node_id == node_id,
                    KnowledgeLinkModel.target_node_id == node_id,
                )
            )
            .all()
        )
        return [self._to_domain(m) for m in models]

    def get_links_between(self, node_id_a: str, node_id_b: str) -> list[KnowledgeLink]:
        """Get all links between two specific nodes (in either direction).

        Args:
            node_id_a: First node ID.
            node_id_b: Second node ID.

        Returns:
            List of KnowledgeLink domain objects connecting the two nodes.
        """
        models = (
            self._session.query(KnowledgeLinkModel)
            .filter(
                or_(
                    (KnowledgeLinkModel.source_node_id == node_id_a)
                    & (KnowledgeLinkModel.target_node_id == node_id_b),
                    (KnowledgeLinkModel.source_node_id == node_id_b)
                    & (KnowledgeLinkModel.target_node_id == node_id_a),
                )
            )
            .all()
        )
        return [self._to_domain(m) for m in models]

    def get_links_for_nodes(self, node_ids: list[str]) -> list[KnowledgeLink]:
        """Get all links where both source and target are in the given node set.

        Useful for getting the subgraph links when filtering.

        Args:
            node_ids: List of node IDs to find links between.

        Returns:
            List of KnowledgeLink domain objects.
        """
        if not node_ids:
            return []

        models = (
            self._session.query(KnowledgeLinkModel)
            .filter(
                KnowledgeLinkModel.source_node_id.in_(node_ids),
                KnowledgeLinkModel.target_node_id.in_(node_ids),
            )
            .all()
        )
        return [self._to_domain(m) for m in models]

    def get_links_by_type(self, link_type: str) -> list[KnowledgeLink]:
        """Get all links of a specific type.

        Args:
            link_type: The link type ("backlink", "tag_shared", "same_book").

        Returns:
            List of KnowledgeLink domain objects.
        """
        models = (
            self._session.query(KnowledgeLinkModel)
            .filter(KnowledgeLinkModel.link_type == link_type)
            .all()
        )
        return [self._to_domain(m) for m in models]

    def delete(self, link_id: str) -> bool:
        """Delete a knowledge link by its ID.

        Returns True if deleted, False if not found.
        """
        model = self._session.get(KnowledgeLinkModel, link_id)
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

    def delete_links_for_node(self, node_id: str) -> int:
        """Delete all links connected to a node.

        Returns the number of links deleted.
        """
        count = (
            self._session.query(KnowledgeLinkModel)
            .filter(
                or_(
                    KnowledgeLinkModel.source_node_id == node_id,
                    KnowledgeLinkModel.target_node_id == node_id,
                )
            )
            .delete(synchronize_session="fetch")
        )
        self._session.flush()
        return count

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _to_domain(self, model: KnowledgeLinkModel) -> KnowledgeLink:
        """Convert an ORM model to a domain entity."""
        return KnowledgeLink(
            id=model.id,
            source_node_id=model.source_node_id,
            target_node_id=model.target_node_id,
            link_type=model.link_type,
            created_at=model.created_at,
        )
