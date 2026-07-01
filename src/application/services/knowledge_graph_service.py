"""Knowledge Graph service implementing the IKnowledgeGraphService protocol.

Orchestrates knowledge graph operations including:
- Graph construction from books, annotations, vocabulary, tags as nodes
- Bidirectional backlink creation and querying
- Graph filtering by tag or book
- Auto-link generation (same-book, shared-tag connections)
- Node neighbor discovery for visualization

Requirements: 9.1–9.5
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.domain.models import KnowledgeLink, KnowledgeNode
from src.domain.value_objects import GraphFilter
from src.infrastructure.database.models import (
    AnnotationModel,
    BookModel,
    TagModel,
    VocabularyEntryModel,
    book_tags,
    annotation_tags,
    vocabulary_tags,
)
from src.infrastructure.repositories.knowledge_repository import (
    KnowledgeLinkRepository,
    KnowledgeNodeRepository,
)


# ---------------------------------------------------------------------------
# Graph result data structures
# ---------------------------------------------------------------------------


@dataclass
class Graph:
    """A graph containing nodes and links for visualization.

    Attributes:
        nodes: All nodes in the graph.
        links: All links (edges) connecting the nodes.
    """

    nodes: list[KnowledgeNode] = field(default_factory=list)
    links: list[KnowledgeLink] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KnowledgeGraphService implementation
# ---------------------------------------------------------------------------


class KnowledgeGraphService:
    """Application-layer service for knowledge graph management.

    Implements the IKnowledgeGraphService protocol from the design document,
    coordinating repositories to handle:
    - Retrieving the full graph or a filtered subgraph for visualization
    - Creating bidirectional backlinks between nodes
    - Querying a node's connections (neighbors)
    - Building graph nodes from existing books, annotations, vocabulary
    - Generating auto-links (same-book, shared-tag connections)
    """

    def __init__(
        self,
        session: Session,
        node_repo: KnowledgeNodeRepository,
        link_repo: KnowledgeLinkRepository,
    ) -> None:
        self._session = session
        self._node_repo = node_repo
        self._link_repo = link_repo

    # ------------------------------------------------------------------
    # Graph retrieval (Requirement 9.1, 9.5)
    # ------------------------------------------------------------------

    def get_graph(self, filter: GraphFilter | None = None) -> Graph:
        """Retrieve the knowledge graph, optionally filtered.

        When no filter is provided, returns all nodes and links.
        When a filter is provided, returns only matching nodes and the
        links that connect them.

        Args:
            filter: Optional filter by tag, book_id, or entity_types.

        Returns:
            A Graph containing the filtered nodes and links.
        """
        if filter is None:
            nodes = self._node_repo.get_all()
            links = self._link_repo.get_all()
            return Graph(nodes=nodes, links=links)

        # Apply filtering
        nodes = self._get_filtered_nodes(filter)
        if not nodes:
            return Graph(nodes=[], links=[])

        # Get links that connect the filtered nodes
        node_ids = [n.id for n in nodes]
        links = self._link_repo.get_links_for_nodes(node_ids)

        return Graph(nodes=nodes, links=links)

    # ------------------------------------------------------------------
    # Backlink creation (Requirement 9.2)
    # ------------------------------------------------------------------

    def create_backlink(self, source_id: str, target_id: str) -> KnowledgeLink:
        """Create a bidirectional backlink between two nodes.

        A backlink is a user-created connection between two knowledge nodes
        (e.g., linking two annotations or a vocabulary entry to an annotation).

        Args:
            source_id: The source node ID.
            target_id: The target node ID.

        Returns:
            The created KnowledgeLink.

        Raises:
            ValueError: If either node does not exist.
        """
        # Validate both nodes exist
        source_node = self._node_repo.get_by_id(source_id)
        if source_node is None:
            raise ValueError(f"Source node '{source_id}' not found.")

        target_node = self._node_repo.get_by_id(target_id)
        if target_node is None:
            raise ValueError(f"Target node '{target_id}' not found.")

        # Check if a link already exists between these nodes
        existing = self._link_repo.get_links_between(source_id, target_id)
        for link in existing:
            if link.link_type == "backlink":
                return link  # Already linked, return existing

        # Create the backlink
        now = datetime.now(UTC)
        link = KnowledgeLink(
            id=str(uuid.uuid4()),
            source_node_id=source_id,
            target_node_id=target_id,
            link_type="backlink",
            created_at=now,
        )
        return self._link_repo.add(link)

    # ------------------------------------------------------------------
    # Node connections / neighbors (Requirement 9.3)
    # ------------------------------------------------------------------

    def get_node_connections(self, node_id: str) -> list[KnowledgeLink]:
        """Get all connections for a specific node (bidirectional).

        Returns all links where the node is either the source or the target,
        enabling navigation to connected entities.

        Args:
            node_id: The node ID to find connections for.

        Returns:
            List of KnowledgeLink domain objects.

        Raises:
            ValueError: If the node does not exist.
        """
        node = self._node_repo.get_by_id(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found.")

        return self._link_repo.get_links_for_node(node_id)

    def get_neighbors(self, node_id: str) -> list[KnowledgeNode]:
        """Get all neighbor nodes connected to a specific node.

        Args:
            node_id: The node ID to find neighbors for.

        Returns:
            List of KnowledgeNode domain objects that are connected.
        """
        links = self._link_repo.get_links_for_node(node_id)

        neighbor_ids: set[str] = set()
        for link in links:
            if link.source_node_id == node_id:
                neighbor_ids.add(link.target_node_id)
            else:
                neighbor_ids.add(link.source_node_id)

        neighbors: list[KnowledgeNode] = []
        for nid in neighbor_ids:
            node = self._node_repo.get_by_id(nid)
            if node is not None:
                neighbors.append(node)

        return neighbors

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        """Get a single node by ID.

        Args:
            node_id: The node's unique ID.

        Returns:
            The KnowledgeNode, or None if not found.
        """
        return self._node_repo.get_by_id(node_id)

    def get_or_create_node(
        self, entity_type: str, entity_id: str, label: str
    ) -> KnowledgeNode:
        """Get an existing node or create a new one for the given entity.

        Args:
            entity_type: The type of entity ("book", "annotation", "vocabulary", "note").
            entity_id: The ID of the entity.
            label: Display label for the node.

        Returns:
            The existing or newly created KnowledgeNode.
        """
        existing = self._node_repo.get_by_entity(entity_type, entity_id)
        if existing is not None:
            return existing

        node = KnowledgeNode(
            id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            label=label,
        )
        return self._node_repo.add(node)

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and all its connections.

        Args:
            node_id: The ID of the node to delete.

        Returns:
            True if deleted, False if not found.
        """
        return self._node_repo.delete(node_id)

    def delete_link(self, link_id: str) -> bool:
        """Delete a specific link.

        Args:
            link_id: The ID of the link to delete.

        Returns:
            True if deleted, False if not found.
        """
        return self._link_repo.delete(link_id)

    # ------------------------------------------------------------------
    # Graph construction (Requirement 9.1, 9.4)
    # ------------------------------------------------------------------

    def build_graph_from_data(self) -> Graph:
        """Build the knowledge graph from existing books, annotations, and vocabulary.

        Creates nodes for all books, annotations, and vocabulary entries that
        don't already have corresponding nodes, and generates auto-links
        (same-book and shared-tag connections).

        Returns:
            The complete Graph after building.
        """
        # Create nodes for all books
        books = self._session.query(BookModel).all()
        for book in books:
            self.get_or_create_node("book", book.id, book.title or "Untitled")

        # Create nodes for all annotations
        annotations = self._session.query(AnnotationModel).all()
        for ann in annotations:
            label = (ann.selected_text or ann.note_content or "")[:50]
            if not label:
                label = f"Annotation ({ann.type})"
            self.get_or_create_node("annotation", ann.id, label)

        # Create nodes for all vocabulary entries
        vocab_entries = self._session.query(VocabularyEntryModel).all()
        for vocab in vocab_entries:
            self.get_or_create_node("vocabulary", vocab.id, vocab.word or "")

        # Generate auto-links
        self._generate_same_book_links()
        self._generate_shared_tag_links()

        return self.get_graph()

    # ------------------------------------------------------------------
    # Auto-link generation (Requirement 9.4)
    # ------------------------------------------------------------------

    def generate_auto_links(self) -> list[KnowledgeLink]:
        """Generate automatic links based on relationships in the data.

        Creates:
        - same_book links: Between entities that belong to the same book
        - tag_shared links: Between entities that share a common tag

        Returns:
            List of newly created KnowledgeLink objects.
        """
        new_links: list[KnowledgeLink] = []
        new_links.extend(self._generate_same_book_links())
        new_links.extend(self._generate_shared_tag_links())
        return new_links

    # ------------------------------------------------------------------
    # Private: Filtering
    # ------------------------------------------------------------------

    def _get_filtered_nodes(self, filter: GraphFilter) -> list[KnowledgeNode]:
        """Get nodes matching the given filter criteria.

        Args:
            filter: Filter by tag, book_id, or entity_types.

        Returns:
            List of matching KnowledgeNode domain objects.
        """
        # Filter by book
        if filter.book_id is not None:
            nodes = self._node_repo.get_nodes_for_book(filter.book_id)
        # Filter by tag
        elif filter.tag is not None:
            nodes = self._node_repo.get_nodes_for_tag(filter.tag)
        # Filter by entity types only
        elif filter.entity_types:
            nodes = self._node_repo.get_all(entity_types=filter.entity_types)
        else:
            nodes = self._node_repo.get_all()

        # Additional entity_types filter (if combined with book/tag filter)
        if filter.entity_types and (filter.book_id or filter.tag):
            nodes = [n for n in nodes if n.entity_type in filter.entity_types]

        return nodes

    # ------------------------------------------------------------------
    # Private: Auto-link generation helpers
    # ------------------------------------------------------------------

    def _generate_same_book_links(self) -> list[KnowledgeLink]:
        """Generate same_book links between entities belonging to the same book.

        Links are created between:
        - Book node ↔ Annotation nodes of that book
        - Book node ↔ Vocabulary nodes from that book

        Returns:
            List of newly created links.
        """
        new_links: list[KnowledgeLink] = []

        books = self._session.query(BookModel).all()
        for book in books:
            book_node = self._node_repo.get_by_entity("book", book.id)
            if book_node is None:
                continue

            # Link book → annotations
            annotations = (
                self._session.query(AnnotationModel)
                .filter(AnnotationModel.book_id == book.id)
                .all()
            )
            for ann in annotations:
                ann_node = self._node_repo.get_by_entity("annotation", ann.id)
                if ann_node is None:
                    continue
                link = self._create_auto_link(
                    book_node.id, ann_node.id, "same_book"
                )
                if link is not None:
                    new_links.append(link)

            # Link book → vocabulary
            vocab_entries = (
                self._session.query(VocabularyEntryModel)
                .filter(VocabularyEntryModel.book_id == book.id)
                .all()
            )
            for vocab in vocab_entries:
                vocab_node = self._node_repo.get_by_entity("vocabulary", vocab.id)
                if vocab_node is None:
                    continue
                link = self._create_auto_link(
                    book_node.id, vocab_node.id, "same_book"
                )
                if link is not None:
                    new_links.append(link)

        return new_links

    def _generate_shared_tag_links(self) -> list[KnowledgeLink]:
        """Generate tag_shared links between entities that share a common tag.

        For each tag, all entities tagged with it are connected to each other
        with tag_shared links.

        Returns:
            List of newly created links.
        """
        new_links: list[KnowledgeLink] = []

        tags = self._session.query(TagModel).all()
        for tag in tags:
            # Collect all node IDs that share this tag
            tagged_node_ids: list[str] = []

            # Books with this tag
            book_ids = [
                row.book_id
                for row in self._session.query(book_tags.c.book_id)
                .filter(book_tags.c.tag_id == tag.id)
                .all()
            ]
            for bid in book_ids:
                node = self._node_repo.get_by_entity("book", bid)
                if node is not None:
                    tagged_node_ids.append(node.id)

            # Annotations with this tag
            ann_ids = [
                row.annotation_id
                for row in self._session.query(annotation_tags.c.annotation_id)
                .filter(annotation_tags.c.tag_id == tag.id)
                .all()
            ]
            for aid in ann_ids:
                node = self._node_repo.get_by_entity("annotation", aid)
                if node is not None:
                    tagged_node_ids.append(node.id)

            # Vocabulary entries with this tag
            vocab_ids = [
                row.vocabulary_id
                for row in self._session.query(vocabulary_tags.c.vocabulary_id)
                .filter(vocabulary_tags.c.tag_id == tag.id)
                .all()
            ]
            for vid in vocab_ids:
                node = self._node_repo.get_by_entity("vocabulary", vid)
                if node is not None:
                    tagged_node_ids.append(node.id)

            # Create pairwise tag_shared links
            for i in range(len(tagged_node_ids)):
                for j in range(i + 1, len(tagged_node_ids)):
                    link = self._create_auto_link(
                        tagged_node_ids[i], tagged_node_ids[j], "tag_shared"
                    )
                    if link is not None:
                        new_links.append(link)

        return new_links

    def _create_auto_link(
        self, source_id: str, target_id: str, link_type: str
    ) -> KnowledgeLink | None:
        """Create an auto-link if one doesn't already exist between the nodes.

        Args:
            source_id: Source node ID.
            target_id: Target node ID.
            link_type: The type of link ("same_book" or "tag_shared").

        Returns:
            The new KnowledgeLink if created, None if a link already exists.
        """
        # Check if link already exists between these nodes with this type
        existing = self._link_repo.get_links_between(source_id, target_id)
        for link in existing:
            if link.link_type == link_type:
                return None  # Already exists

        now = datetime.now(UTC)
        link = KnowledgeLink(
            id=str(uuid.uuid4()),
            source_node_id=source_id,
            target_node_id=target_id,
            link_type=link_type,
            created_at=now,
        )
        return self._link_repo.add(link)
