"""Annotation QML controller bridging AnnotationService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for annotation management including:
- Context menu display on text selection (highlight, underline, note, copy, dictionary)
- Annotation panel showing all annotations grouped by chapter/page
- Annotation rendering integration with PDF (overlay coordinates) and EPUB (CSS highlight injection)

Requirements: 2.8, 2.9, 3.7, 3.8, 5.2, 5.3, 5.6
"""

from __future__ import annotations

import json

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.annotation_service import AnnotationService
from src.domain.enums import AnnotationType, HighlightColor
from src.domain.models import Annotation
from src.domain.value_objects import TextPosition


class AnnotationListModel(QAbstractListModel):
    """QAbstractListModel exposing annotations to QML.

    Displays annotations grouped by chapter/page in chronological order.

    Roles:
        IdRole - annotation unique ID
        TypeRole - annotation type (highlight, underline, note, comment)
        ColorRole - highlight color name
        SelectedTextRole - the annotated text
        NoteContentRole - associated note content
        PageRole - page number (for PDF)
        ChapterRole - chapter identifier (for EPUB)
        CreatedAtRole - creation timestamp as ISO string
        PositionDataRole - raw position JSON
    """

    IdRole = Qt.ItemDataRole.UserRole + 1
    TypeRole = Qt.ItemDataRole.UserRole + 2
    ColorRole = Qt.ItemDataRole.UserRole + 3
    SelectedTextRole = Qt.ItemDataRole.UserRole + 4
    NoteContentRole = Qt.ItemDataRole.UserRole + 5
    PageRole = Qt.ItemDataRole.UserRole + 6
    ChapterRole = Qt.ItemDataRole.UserRole + 7
    CreatedAtRole = Qt.ItemDataRole.UserRole + 8
    PositionDataRole = Qt.ItemDataRole.UserRole + 9

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._annotations: list[Annotation] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._annotations)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._annotations):
            return None

        annotation = self._annotations[index.row()]

        if role == self.IdRole:
            return annotation.id
        elif role == self.TypeRole:
            return annotation.type.value
        elif role == self.ColorRole:
            return annotation.color.value if annotation.color else ""
        elif role == self.SelectedTextRole:
            return annotation.selected_text
        elif role == self.NoteContentRole:
            return annotation.note_content or ""
        elif role == self.PageRole:
            return self._get_page(annotation)
        elif role == self.ChapterRole:
            return self._get_chapter(annotation)
        elif role == self.CreatedAtRole:
            return annotation.created_at.isoformat()
        elif role == self.PositionDataRole:
            return annotation.position_data
        elif role == Qt.ItemDataRole.DisplayRole:
            return annotation.selected_text

        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.IdRole: b"annotationId",
            self.TypeRole: b"annotationType",
            self.ColorRole: b"annotationColor",
            self.SelectedTextRole: b"selectedText",
            self.NoteContentRole: b"noteContent",
            self.PageRole: b"page",
            self.ChapterRole: b"chapter",
            self.CreatedAtRole: b"createdAt",
            self.PositionDataRole: b"positionData",
        }

    def set_annotations(self, annotations: list[Annotation]) -> None:
        """Replace annotations and notify views."""
        self.beginResetModel()
        self._annotations = list(annotations)
        self.endResetModel()

    def get_annotations(self) -> list[Annotation]:
        """Return the current list of annotations."""
        return list(self._annotations)

    @staticmethod
    def _get_page(annotation: Annotation) -> int:
        """Extract page number from position data. Returns -1 if not available."""
        try:
            pos = json.loads(annotation.position_data)
            page = pos.get("page")
            return page if page is not None else -1
        except (json.JSONDecodeError, TypeError):
            return -1

    @staticmethod
    def _get_chapter(annotation: Annotation) -> str:
        """Extract chapter identifier from position data. Returns empty string if not available."""
        try:
            pos = json.loads(annotation.position_data)
            return pos.get("chapter") or ""
        except (json.JSONDecodeError, TypeError):
            return ""


class AnnotationController(QObject):
    """QObject controller for annotation management in QML.

    Bridges the AnnotationService to the QML presentation layer,
    providing slots for creating annotations from text selections,
    managing the annotation panel, and rendering annotations in readers.

    Requirements: 2.8, 2.9, 3.7, 3.8, 5.2, 5.3, 5.6
    """

    # Signals
    annotationsChanged = Signal()
    annotationCreated = Signal(str)  # annotation ID
    annotationDeleted = Signal(str)  # annotation ID
    contextMenuRequested = Signal(float, float)  # x, y position for context menu
    errorOccurred = Signal(str)  # error message
    exportReady = Signal(str)  # exported Markdown content

    # Signals for reader integration
    pdfOverlaysChanged = Signal()  # PDF overlay annotations changed
    epubCssChanged = Signal(str)  # EPUB CSS highlight injection string

    def __init__(
        self,
        annotation_service: AnnotationService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = annotation_service
        self._annotation_model = AnnotationListModel(self)
        self._current_book_id: str = ""
        self._selected_text: str = ""
        self._selection_page: int = -1
        self._selection_chapter: str = ""
        self._selection_start_offset: int = 0
        self._selection_end_offset: int = 0
        self._context_menu_visible: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(QObject, constant=True)
    def annotationModel(self) -> AnnotationListModel:  # noqa: N802
        """The annotation list model for QML binding."""
        return self._annotation_model

    @Property(str, notify=annotationsChanged)
    def currentBookId(self) -> str:  # noqa: N802
        """The current book ID for which annotations are loaded."""
        return self._current_book_id

    @Property(str, notify=contextMenuRequested)
    def selectedText(self) -> str:  # noqa: N802
        """The currently selected text."""
        return self._selected_text

    @Property(bool, notify=contextMenuRequested)
    def contextMenuVisible(self) -> bool:  # noqa: N802
        """Whether the context menu is currently visible."""
        return self._context_menu_visible

    @Property(int, notify=annotationsChanged)
    def annotationCount(self) -> int:  # noqa: N802
        """Number of annotations for the current book."""
        return self._annotation_model.rowCount()

    # ------------------------------------------------------------------
    # Slots - Book and Selection Management
    # ------------------------------------------------------------------

    @Slot(str)
    def loadAnnotations(self, book_id: str) -> None:  # noqa: N802
        """Load all annotations for a book.

        Args:
            book_id: The book ID to load annotations for.
        """
        self._current_book_id = book_id
        if self._service is None:
            self._annotation_model.set_annotations([])
            self.annotationsChanged.emit()
            return

        annotations = self._service.get_annotations(book_id)
        self._annotation_model.set_annotations(annotations)
        self.annotationsChanged.emit()
        # Emit reader integration signals
        self.pdfOverlaysChanged.emit()
        self._emit_epub_css(annotations)

    @Slot(str, int, str, int, int, float, float)
    def onTextSelected(  # noqa: N802
        self,
        text: str,
        page: int,
        chapter: str,
        start_offset: int,
        end_offset: int,
        x: float,
        y: float,
    ) -> None:
        """Handle text selection event from reader.

        Stores the selection state and requests context menu display.

        Args:
            text: The selected text.
            page: Page number (-1 if not applicable, e.g., EPUB).
            chapter: Chapter identifier (empty if not applicable, e.g., PDF).
            start_offset: Start character offset.
            end_offset: End character offset.
            x: X position for context menu placement.
            y: Y position for context menu placement.
        """
        self._selected_text = text
        self._selection_page = page
        self._selection_chapter = chapter
        self._selection_start_offset = start_offset
        self._selection_end_offset = end_offset
        self._context_menu_visible = True
        self.contextMenuRequested.emit(x, y)

    @Slot()
    def dismissContextMenu(self) -> None:  # noqa: N802
        """Hide the context menu."""
        self._context_menu_visible = False
        self.contextMenuRequested.emit(-1, -1)

    # ------------------------------------------------------------------
    # Slots - Annotation Creation (Context Menu Actions)
    # ------------------------------------------------------------------

    @Slot(str)
    def highlightSelection(self, color: str) -> None:  # noqa: N802
        """Apply a highlight annotation to the current selection.

        Args:
            color: Highlight color name (yellow, green, blue, pink, orange).
        """
        self._create_annotation(AnnotationType.HIGHLIGHT, color)

    @Slot()
    def underlineSelection(self) -> None:  # noqa: N802
        """Apply an underline annotation to the current selection."""
        self._create_annotation(AnnotationType.UNDERLINE, None)

    @Slot(str)
    def addNoteToSelection(self, note_content: str) -> None:  # noqa: N802
        """Add a note annotation to the current selection.

        Args:
            note_content: The note text to attach to the selection.
        """
        self._create_annotation(AnnotationType.NOTE, None, note_content)

    @Slot(str, str)
    def addHighlightWithNote(self, color: str, note_content: str) -> None:  # noqa: N802
        """Apply a highlight with an attached note.

        Args:
            color: Highlight color name.
            note_content: The note text.
        """
        self._create_annotation(AnnotationType.HIGHLIGHT, color, note_content)

    # ------------------------------------------------------------------
    # Slots - Annotation Management
    # ------------------------------------------------------------------

    @Slot(str)
    def deleteAnnotation(self, annotation_id: str) -> None:  # noqa: N802
        """Delete an annotation by ID.

        Args:
            annotation_id: The annotation to delete.
        """
        if self._service is None:
            self.errorOccurred.emit("Annotation service not available")
            return

        try:
            self._service.delete_annotation(annotation_id)
            self.annotationDeleted.emit(annotation_id)
            # Refresh annotations list
            self.loadAnnotations(self._current_book_id)
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str, str)
    def addComment(self, annotation_id: str, content: str) -> None:  # noqa: N802
        """Add a comment to an existing annotation.

        Args:
            annotation_id: The annotation to comment on.
            content: The comment text.
        """
        if self._service is None:
            self.errorOccurred.emit("Annotation service not available")
            return

        try:
            self._service.add_comment(annotation_id, content)
            self.annotationsChanged.emit()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str, str)
    def addTag(self, annotation_id: str, tag: str) -> None:  # noqa: N802
        """Add a tag to an annotation.

        Args:
            annotation_id: The annotation to tag.
            tag: The tag name.
        """
        if self._service is None:
            self.errorOccurred.emit("Annotation service not available")
            return

        try:
            self._service.add_tag(annotation_id, tag)
            self.annotationsChanged.emit()
        except ValueError as e:
            self.errorOccurred.emit(str(e))

    @Slot()
    def exportAnnotations(self) -> None:  # noqa: N802
        """Export all annotations for the current book as Markdown."""
        if self._service is None:
            self.errorOccurred.emit("Annotation service not available")
            return

        if not self._current_book_id:
            self.errorOccurred.emit("No book loaded")
            return

        markdown = self._service.export_markdown(self._current_book_id)
        self.exportReady.emit(markdown)

    # ------------------------------------------------------------------
    # Slots - Reader Integration
    # ------------------------------------------------------------------

    @Slot(result=str)
    def getPdfOverlays(self) -> str:  # noqa: N802
        """Get PDF annotation overlays as JSON for rendering.

        Returns a JSON array of annotation overlay objects with:
        - id: annotation ID
        - type: annotation type
        - color: highlight color
        - page: page number
        - start_offset: start character offset
        - end_offset: end character offset

        Returns:
            JSON string of overlay annotations for the current book.
        """
        annotations = self._annotation_model.get_annotations()
        overlays = []
        for ann in annotations:
            try:
                pos = json.loads(ann.position_data)
                if pos.get("page") is not None:
                    overlays.append({
                        "id": ann.id,
                        "type": ann.type.value,
                        "color": ann.color.value if ann.color else "yellow",
                        "page": pos["page"],
                        "start_offset": pos.get("start_offset", 0),
                        "end_offset": pos.get("end_offset", 0),
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        return json.dumps(overlays)

    @Slot(result=str)
    def getEpubHighlightCss(self) -> str:  # noqa: N802
        """Get CSS for EPUB annotation highlight injection.

        Generates CSS rules that highlight annotated text ranges in
        the EPUB content. Uses data attributes for targeting specific
        text ranges.

        Returns:
            CSS string for injecting into EPUB QWebEngine content.
        """
        annotations = self._annotation_model.get_annotations()
        return self._generate_epub_css(annotations)

    @Slot(int, result=str)
    def getPageAnnotations(self, page: int) -> str:  # noqa: N802
        """Get annotations for a specific PDF page as JSON.

        Args:
            page: Page number (0-indexed).

        Returns:
            JSON array of annotations on the specified page.
        """
        annotations = self._annotation_model.get_annotations()
        page_annotations = []
        for ann in annotations:
            try:
                pos = json.loads(ann.position_data)
                if pos.get("page") == page:
                    page_annotations.append({
                        "id": ann.id,
                        "type": ann.type.value,
                        "color": ann.color.value if ann.color else "yellow",
                        "selectedText": ann.selected_text,
                        "startOffset": pos.get("start_offset", 0),
                        "endOffset": pos.get("end_offset", 0),
                        "noteContent": ann.note_content or "",
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        return json.dumps(page_annotations)

    @Slot(str, result=str)
    def getChapterAnnotations(self, chapter: str) -> str:  # noqa: N802
        """Get annotations for a specific EPUB chapter as JSON.

        Args:
            chapter: Chapter identifier.

        Returns:
            JSON array of annotations in the specified chapter.
        """
        annotations = self._annotation_model.get_annotations()
        chapter_annotations = []
        for ann in annotations:
            try:
                pos = json.loads(ann.position_data)
                if pos.get("chapter") == chapter:
                    chapter_annotations.append({
                        "id": ann.id,
                        "type": ann.type.value,
                        "color": ann.color.value if ann.color else "yellow",
                        "selectedText": ann.selected_text,
                        "startOffset": pos.get("start_offset", 0),
                        "endOffset": pos.get("end_offset", 0),
                        "noteContent": ann.note_content or "",
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        return json.dumps(chapter_annotations)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_annotation(
        self,
        ann_type: AnnotationType,
        color: str | None,
        note_content: str | None = None,
    ) -> None:
        """Create an annotation from the current text selection state.

        Args:
            ann_type: The type of annotation to create.
            color: Optional color name for highlights.
            note_content: Optional note text for note annotations.
        """
        if self._service is None:
            self.errorOccurred.emit("Annotation service not available")
            return

        if not self._selected_text:
            self.errorOccurred.emit("No text selected")
            return

        if not self._current_book_id:
            self.errorOccurred.emit("No book loaded")
            return

        # Resolve color enum
        highlight_color: HighlightColor | None = None
        if color:
            try:
                highlight_color = HighlightColor(color)
            except ValueError:
                highlight_color = HighlightColor.YELLOW

        # Build text position
        position = TextPosition(
            page=self._selection_page if self._selection_page >= 0 else None,
            chapter=self._selection_chapter or None,
            start_offset=self._selection_start_offset,
            end_offset=self._selection_end_offset,
        )

        # Determine content: for notes, use note_content; for highlights, use selected text
        content = note_content if ann_type == AnnotationType.NOTE else self._selected_text

        try:
            annotation = self._service.create_annotation(
                book_id=self._current_book_id,
                position=position,
                ann_type=ann_type,
                color=highlight_color,
                content=content,
            )
            self.annotationCreated.emit(annotation.id)
            # Refresh annotations list
            self.loadAnnotations(self._current_book_id)
            # Dismiss context menu after action
            self.dismissContextMenu()
        except Exception as e:
            self.errorOccurred.emit(str(e))

    def _emit_epub_css(self, annotations: list[Annotation]) -> None:
        """Generate and emit EPUB CSS for highlight rendering.

        Args:
            annotations: List of annotations to render as CSS.
        """
        css = self._generate_epub_css(annotations)
        self.epubCssChanged.emit(css)

    @staticmethod
    def _generate_epub_css(annotations: list[Annotation]) -> str:
        """Generate CSS rules for EPUB annotation highlight injection.

        Creates CSS classes targeting annotation spans by ID, applying
        background colors for highlights and border-bottom for underlines.

        Args:
            annotations: List of annotations to generate CSS for.

        Returns:
            CSS string with highlight/underline styles.
        """
        color_map = {
            HighlightColor.YELLOW: "rgba(255, 255, 0, 0.35)",
            HighlightColor.GREEN: "rgba(0, 255, 0, 0.25)",
            HighlightColor.BLUE: "rgba(0, 150, 255, 0.25)",
            HighlightColor.PINK: "rgba(255, 105, 180, 0.30)",
            HighlightColor.ORANGE: "rgba(255, 165, 0, 0.30)",
        }

        css_rules: list[str] = []

        for ann in annotations:
            try:
                pos = json.loads(ann.position_data)
            except (json.JSONDecodeError, TypeError):
                continue

            # Only generate CSS for EPUB annotations (chapter-based)
            if pos.get("chapter") is None and pos.get("page") is not None:
                continue

            ann_id = ann.id.replace("-", "")

            if ann.type == AnnotationType.HIGHLIGHT:
                bg_color = color_map.get(
                    ann.color, "rgba(255, 255, 0, 0.35)"
                )
                css_rules.append(
                    f".annotation-{ann_id} {{ "
                    f"background-color: {bg_color}; "
                    f"border-radius: 2px; "
                    f"}}"
                )
            elif ann.type == AnnotationType.UNDERLINE:
                css_rules.append(
                    f".annotation-{ann_id} {{ "
                    f"border-bottom: 2px solid #333; "
                    f"padding-bottom: 1px; "
                    f"}}"
                )
            elif ann.type == AnnotationType.NOTE:
                bg_color = "rgba(255, 255, 150, 0.20)"
                css_rules.append(
                    f".annotation-{ann_id} {{ "
                    f"background-color: {bg_color}; "
                    f"border-bottom: 1px dashed #999; "
                    f"}}"
                )

        return "\n".join(css_rules)
