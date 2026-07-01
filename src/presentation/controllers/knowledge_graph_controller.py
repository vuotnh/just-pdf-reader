"""Knowledge Graph QML controller bridging KnowledgeGraphService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for knowledge graph visualization including:
- Graph data exposed as JSON for Canvas rendering
- Filter slots (by tag, book)
- Node click navigation signals
- Graph update within 500ms of new data

Requirements: 9.1–9.5, 14.1
"""

from __future__ import annotations

import json
import logging
import time

from PySide6.QtCore import (
    QObject,
    QTimer,
    Property,
    Signal,
    Slot,
)

from src.application.services.knowledge_graph_service import Graph, KnowledgeGraphService
from src.domain.models import KnowledgeLink, KnowledgeNode
from src.domain.value_objects import GraphFilter

logger = logging.getLogger(__name__)


class KnowledgeGraphController(QObject):
    """QObject controller bridging KnowledgeGraphService to QML.

    Exposes knowledge graph data as JSON properties for Canvas-based
    rendering in QML. Provides filter slots, node navigation signals,
    and ensures graph updates are delivered within 500ms of data changes.

    The controller serializes graph nodes and links to JSON format that
    the QML Canvas uses to render a force-directed layout.

    Requirements: 9.1–9.5, 14.1
    """

    # Signals
    graphChanged = Signal()
    filterChanged = Signal()
    navigateToBook = Signal(str)  # book_id
    navigateToAnnotation = Signal(str, str)  # annotation_id, book_id
    navigateToVocabulary = Signal(str)  # entry_id
    nodeClicked = Signal(str, str, str)  # node_id, entity_type, entity_id
    errorOccurred = Signal(str)  # error message

    def __init__(
        self,
        knowledge_graph_service: KnowledgeGraphService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = knowledge_graph_service
        self._nodes_json: str = "[]"
        self._links_json: str = "[]"
        self._node_count: int = 0
        self._link_count: int = 0
        self._filter_tag: str = ""
        self._filter_book_id: str = ""
        self._is_loading: bool = False

        # Debounce timer for graph updates (ensures 500ms target)
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(100)  # 100ms debounce for rapid changes
        self._update_timer.timeout.connect(self._do_refresh_graph)

        # Load initial graph
        self._refresh_graph()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(str, notify=graphChanged)
    def nodesJson(self) -> str:  # noqa: N802
        """JSON array of graph nodes for QML Canvas rendering.

        Each node object contains:
        - id: unique node identifier
        - entityType: "book", "annotation", "vocabulary", or "note"
        - entityId: the ID of the underlying entity
        - label: display label for the node
        """
        return self._nodes_json

    @Property(str, notify=graphChanged)
    def linksJson(self) -> str:  # noqa: N802
        """JSON array of graph links for QML Canvas rendering.

        Each link object contains:
        - id: unique link identifier
        - sourceNodeId: source node ID
        - targetNodeId: target node ID
        - linkType: "backlink", "same_book", or "tag_shared"
        """
        return self._links_json

    @Property(int, notify=graphChanged)
    def nodeCount(self) -> int:  # noqa: N802
        """Number of nodes currently in the graph."""
        return self._node_count

    @Property(int, notify=graphChanged)
    def linkCount(self) -> int:  # noqa: N802
        """Number of links currently in the graph."""
        return self._link_count

    @Property(bool, notify=graphChanged)
    def isLoading(self) -> bool:  # noqa: N802
        """Whether the graph is currently being loaded."""
        return self._is_loading

    @Property(str, notify=filterChanged)
    def filterTag(self) -> str:  # noqa: N802
        """Current tag filter value."""
        return self._filter_tag

    @Property(str, notify=filterChanged)
    def filterBookId(self) -> str:  # noqa: N802
        """Current book filter value."""
        return self._filter_book_id

    # ------------------------------------------------------------------
    # Slots - Filtering
    # ------------------------------------------------------------------

    @Slot(str)
    def setFilterTag(self, tag: str) -> None:  # noqa: N802
        """Set the tag filter for the knowledge graph.

        Args:
            tag: Tag name to filter by, or empty string to clear.
        """
        self._filter_tag = tag
        self.filterChanged.emit()
        self._schedule_refresh()

    @Slot(str)
    def setFilterBookId(self, book_id: str) -> None:  # noqa: N802
        """Set the book filter for the knowledge graph.

        Args:
            book_id: Book ID to filter by, or empty string to clear.
        """
        self._filter_book_id = book_id
        self.filterChanged.emit()
        self._schedule_refresh()

    @Slot()
    def clearFilters(self) -> None:  # noqa: N802
        """Clear all active filters and show the full graph."""
        self._filter_tag = ""
        self._filter_book_id = ""
        self.filterChanged.emit()
        self._schedule_refresh()

    # ------------------------------------------------------------------
    # Slots - Graph Operations
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        """Manually refresh the graph data from the service."""
        self._refresh_graph()

    @Slot()
    def buildGraph(self) -> None:  # noqa: N802
        """Build the knowledge graph from existing data.

        Generates nodes for all books, annotations, and vocabulary entries,
        then creates auto-links (same_book, tag_shared connections).
        """
        if self._service is None:
            self.errorOccurred.emit("Knowledge graph service not available")
            return

        try:
            self._service.build_graph_from_data()
            self._refresh_graph()
        except Exception as e:
            logger.exception("Failed to build knowledge graph")
            self.errorOccurred.emit(f"Failed to build graph: {e}")

    @Slot(str, str)
    def createBacklink(self, source_id: str, target_id: str) -> None:  # noqa: N802
        """Create a bidirectional backlink between two nodes.

        Args:
            source_id: The source node ID.
            target_id: The target node ID.
        """
        if self._service is None:
            self.errorOccurred.emit("Knowledge graph service not available")
            return

        try:
            self._service.create_backlink(source_id, target_id)
            self._schedule_refresh()
        except ValueError as e:
            self.errorOccurred.emit(str(e))
        except Exception as e:
            logger.exception("Failed to create backlink")
            self.errorOccurred.emit(f"Failed to create backlink: {e}")

    # ------------------------------------------------------------------
    # Slots - Node Navigation
    # ------------------------------------------------------------------

    @Slot(str)
    def onNodeClicked(self, node_id: str) -> None:  # noqa: N802
        """Handle a node click event from the QML graph view.

        Resolves the node's entity type and emits the appropriate
        navigation signal to open the corresponding view.

        Args:
            node_id: The ID of the clicked node.
        """
        if self._service is None:
            return

        try:
            node = self._service.get_node(node_id)
            if node is None:
                logger.warning("Clicked node not found: %s", node_id)
                return

            self.nodeClicked.emit(node_id, node.entity_type, node.entity_id)

            if node.entity_type == "book":
                self.navigateToBook.emit(node.entity_id)
            elif node.entity_type == "annotation":
                # For annotations, we emit the annotation_id; book_id is resolved by the view
                self.navigateToAnnotation.emit(node.entity_id, "")
            elif node.entity_type == "vocabulary":
                self.navigateToVocabulary.emit(node.entity_id)
            elif node.entity_type == "note":
                # Notes are a type of annotation
                self.navigateToAnnotation.emit(node.entity_id, "")
            else:
                logger.warning("Unknown entity type for navigation: %s", node.entity_type)
        except Exception as e:
            logger.exception("Error handling node click: %s", node_id)
            self.errorOccurred.emit(f"Navigation failed: {e}")

    # ------------------------------------------------------------------
    # Slots - Query
    # ------------------------------------------------------------------

    @Slot(str, result=str)
    def getNodeJson(self, node_id: str) -> str:  # noqa: N802
        """Get a single node's data as JSON.

        Args:
            node_id: The node ID to retrieve.

        Returns:
            JSON string with node data, or empty string if not found.
        """
        if self._service is None:
            return ""

        node = self._service.get_node(node_id)
        if node is None:
            return ""

        return json.dumps(
            {
                "id": node.id,
                "entityType": node.entity_type,
                "entityId": node.entity_id,
                "label": node.label,
            },
            ensure_ascii=False,
        )

    @Slot(str, result=str)
    def getNodeNeighborsJson(self, node_id: str) -> str:  # noqa: N802
        """Get all neighbors of a node as JSON.

        Args:
            node_id: The node ID to find neighbors for.

        Returns:
            JSON array of neighbor node objects.
        """
        if self._service is None:
            return "[]"

        try:
            neighbors = self._service.get_neighbors(node_id)
            return json.dumps(
                [
                    {
                        "id": n.id,
                        "entityType": n.entity_type,
                        "entityId": n.entity_id,
                        "label": n.label,
                    }
                    for n in neighbors
                ],
                ensure_ascii=False,
            )
        except ValueError:
            return "[]"

    # ------------------------------------------------------------------
    # Public method for external notification of data changes
    # ------------------------------------------------------------------

    def notify_data_changed(self) -> None:
        """Notify the controller that graph data has changed.

        Schedules a graph refresh within 500ms to meet the
        update latency requirement (Requirement 9.4).
        """
        self._schedule_refresh()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _schedule_refresh(self) -> None:
        """Schedule a debounced graph refresh.

        Uses a timer to coalesce rapid changes while still meeting
        the 500ms update target (Requirement 9.4).
        """
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _refresh_graph(self) -> None:
        """Immediately refresh the graph data from the service."""
        self._do_refresh_graph()

    def _do_refresh_graph(self) -> None:
        """Execute the graph refresh, serializing data to JSON for QML."""
        if self._service is None:
            self._nodes_json = "[]"
            self._links_json = "[]"
            self._node_count = 0
            self._link_count = 0
            self.graphChanged.emit()
            return

        self._is_loading = True
        self.graphChanged.emit()

        start_time = time.perf_counter()

        try:
            # Build filter from current state
            graph_filter = self._build_filter()
            graph = self._service.get_graph(filter=graph_filter)

            # Serialize nodes to JSON
            self._nodes_json = json.dumps(
                [self._serialize_node(node) for node in graph.nodes],
                ensure_ascii=False,
            )

            # Serialize links to JSON
            self._links_json = json.dumps(
                [self._serialize_link(link) for link in graph.links],
                ensure_ascii=False,
            )

            self._node_count = len(graph.nodes)
            self._link_count = len(graph.links)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if elapsed_ms > 500:
                logger.warning(
                    "Graph update took %.1fms (target: 500ms)", elapsed_ms
                )

        except Exception as e:
            logger.exception("Failed to refresh knowledge graph")
            self.errorOccurred.emit(f"Graph refresh failed: {e}")
        finally:
            self._is_loading = False
            self.graphChanged.emit()

    def _build_filter(self) -> GraphFilter | None:
        """Build a GraphFilter from the current filter state."""
        tag = self._filter_tag or None
        book_id = self._filter_book_id or None

        if tag or book_id:
            return GraphFilter(tag=tag, book_id=book_id)
        return None

    @staticmethod
    def _serialize_node(node: KnowledgeNode) -> dict:
        """Serialize a KnowledgeNode to a dict for JSON output."""
        return {
            "id": node.id,
            "entityType": node.entity_type,
            "entityId": node.entity_id,
            "label": node.label,
        }

    @staticmethod
    def _serialize_link(link: KnowledgeLink) -> dict:
        """Serialize a KnowledgeLink to a dict for JSON output."""
        return {
            "id": link.id,
            "sourceNodeId": link.source_node_id,
            "targetNodeId": link.target_node_id,
            "linkType": link.link_type,
        }
