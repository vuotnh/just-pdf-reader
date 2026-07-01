"""PDF Reader QML controller bridging PDFReaderBackend to QML views.

Provides a QObject-based controller with signals, slots, and properties
for PDF rendering, navigation, zoom, search, and TOC operations.
Includes a QML Image Provider for rendering pages into QML Image elements.

Requirements: 2.1–2.6, 14.1
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from src.infrastructure.readers.pdf_reader_backend import (
    PDFReaderBackend,
    RenderedPage,
    SearchMatch,
    SearchNavigator,
    TocEntry,
    ViewMode,
)


class TocListModel(QAbstractListModel):
    """QAbstractListModel exposing PDF TOC entries to QML.

    Roles:
        TitleRole - the section title
        LevelRole - nesting level (1-based)
        PageNumberRole - target page (0-indexed)
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    LevelRole = Qt.ItemDataRole.UserRole + 2
    PageNumberRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[TocEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None

        entry = self._entries[index.row()]

        if role == self.TitleRole:
            return entry.title
        elif role == self.LevelRole:
            return entry.level
        elif role == self.PageNumberRole:
            return entry.page_number
        elif role == Qt.ItemDataRole.DisplayRole:
            return entry.title

        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.LevelRole: b"level",
            self.PageNumberRole: b"pageNumber",
        }

    def set_entries(self, entries: list[TocEntry]) -> None:
        """Replace TOC entries and notify views."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def get_entries(self) -> list[TocEntry]:
        """Return the current list of TOC entries."""
        return list(self._entries)


class PDFPageImageProvider(QQuickImageProvider):
    """QML Image Provider that renders PDF pages on demand.

    QML requests images via: "image://pdfpage/<page_number>"
    The provider uses the PDFReaderBackend to render the requested page
    at the current zoom level.
    """

    def __init__(self, backend: PDFReaderBackend) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._backend = backend

    def requestImage(self, id: str, size, requestedSize):
        """Render a PDF page as a QImage for QML display.

        Args:
            id: The page number as a string (0-indexed).
            size: Output size (set by this method).
            requestedSize: Requested size from QML (ignored, we use zoom).

        Returns:
            Tuple of (QImage, actual_size).
        """
        try:
            page_number = int(id.split("/")[0]) if "/" in id else int(id)
        except (ValueError, IndexError):
            # Return an empty image on invalid request
            return QImage(), size

        if self._backend.document is None:
            return QImage(), size

        if page_number < 0 or page_number >= self._backend.page_count:
            return QImage(), size

        rendered = self._backend.render_page(page_number)
        image = self._rendered_page_to_qimage(rendered)
        return image, image.size()

    @staticmethod
    def _rendered_page_to_qimage(rendered: RenderedPage) -> QImage:
        """Convert a RenderedPage to a QImage.

        Args:
            rendered: The rendered page with pixel data.

        Returns:
            A QImage in the appropriate format.
        """
        if rendered.samples == 4:
            fmt = QImage.Format.Format_RGBA8888
        else:
            fmt = QImage.Format.Format_RGB888

        image = QImage(
            rendered.pixel_data,
            rendered.width,
            rendered.height,
            rendered.width * rendered.samples,
            fmt,
        )
        # QImage doesn't take ownership of data, so we need a copy
        return image.copy()


class PDFReaderController(QObject):
    """QObject controller bridging PDFReaderBackend to QML.

    Exposes PDF reader operations as slots callable from QML and emits
    signals to notify the UI of state changes. Manages the backend,
    search navigator, and TOC model.
    """

    # Signals
    documentOpened = Signal()
    documentClosed = Signal()
    pageChanged = Signal(int)  # new page number (0-indexed)
    pageCountChanged = Signal(int)
    zoomChanged = Signal(float)  # new zoom level
    viewModeChanged = Signal(str)  # "single_page" or "continuous_scroll"
    searchResultsChanged = Signal(int)  # total match count
    currentMatchChanged = Signal(int)  # current match index
    errorOccurred = Signal(str)  # error message

    def __init__(
        self,
        backend: PDFReaderBackend | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend or PDFReaderBackend()
        self._search_navigator = SearchNavigator()
        self._toc_model = TocListModel(self)
        self._image_provider = PDFPageImageProvider(self._backend)

    # ------------------------------------------------------------------
    # Properties (read-only, notified by signals)
    # ------------------------------------------------------------------

    @Property(int, notify=pageChanged)
    def currentPage(self) -> int:  # noqa: N802
        """Current page number (0-indexed)."""
        return self._backend.current_page

    @Property(int, notify=pageCountChanged)
    def pageCount(self) -> int:  # noqa: N802
        """Total number of pages in the document."""
        return self._backend.page_count

    @Property(float, notify=zoomChanged)
    def zoomLevel(self) -> float:  # noqa: N802
        """Current zoom level as a multiplier (1.0 = 100%)."""
        return self._backend.zoom_level

    @Property(str, notify=viewModeChanged)
    def viewMode(self) -> str:  # noqa: N802
        """Current view mode as a string."""
        return self._backend.view_mode.value

    @Property(int, notify=searchResultsChanged)
    def searchMatchCount(self) -> int:  # noqa: N802
        """Total number of search matches."""
        return self._search_navigator.match_count

    @Property(int, notify=currentMatchChanged)
    def currentMatchIndex(self) -> int:  # noqa: N802
        """Index of the current search match (-1 if none)."""
        return self._search_navigator.current_index

    @Property(QObject, constant=True)
    def tocModel(self) -> TocListModel:  # noqa: N802
        """The TOC list model for QML binding."""
        return self._toc_model

    # ------------------------------------------------------------------
    # Public accessors (non-QML)
    # ------------------------------------------------------------------

    @property
    def backend(self) -> PDFReaderBackend:
        """The underlying PDF reader backend."""
        return self._backend

    @property
    def image_provider(self) -> PDFPageImageProvider:
        """The QML image provider for PDF pages."""
        return self._image_provider

    @property
    def search_navigator(self) -> SearchNavigator:
        """The search navigator for result traversal."""
        return self._search_navigator

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def openPdf(self, file_path: str) -> None:  # noqa: N802
        """Open a PDF document.

        Args:
            file_path: Path to the PDF file.
        """
        try:
            self._backend.open(file_path)
            # Load table of contents
            toc_entries = self._backend.get_toc()
            self._toc_model.set_entries(toc_entries)
            # Reset search
            self._search_navigator.set_matches([])
            # Emit signals
            self.pageCountChanged.emit(self._backend.page_count)
            self.pageChanged.emit(self._backend.current_page)
            self.zoomChanged.emit(self._backend.zoom_level)
            self.documentOpened.emit()
        except (RuntimeError, FileNotFoundError) as e:
            self.errorOccurred.emit(str(e))

    @Slot()
    def closePdf(self) -> None:  # noqa: N802
        """Close the current PDF document."""
        self._backend.close()
        self._toc_model.set_entries([])
        self._search_navigator.set_matches([])
        self.documentClosed.emit()
        self.pageCountChanged.emit(0)

    @Slot(float)
    def setZoom(self, zoom: float) -> None:  # noqa: N802
        """Set the zoom level, clamping to valid range.

        Args:
            zoom: Requested zoom level as a multiplier.
        """
        actual = self._backend.set_zoom(zoom)
        self.zoomChanged.emit(actual)

    @Slot()
    def zoomFitWidth(self) -> None:  # noqa: N802
        """Set zoom to fit page width in viewport."""
        actual = self._backend.set_zoom_fit_width()
        self.zoomChanged.emit(actual)

    @Slot()
    def zoomFitPage(self) -> None:  # noqa: N802
        """Set zoom to fit entire page in viewport."""
        actual = self._backend.set_zoom_fit_page()
        self.zoomChanged.emit(actual)

    @Slot(str)
    def setPageMode(self, mode: str) -> None:  # noqa: N802
        """Set the view mode.

        Args:
            mode: "single_page" or "continuous_scroll".
        """
        try:
            view_mode = ViewMode(mode)
            self._backend.set_view_mode(view_mode)
            self.viewModeChanged.emit(mode)
        except ValueError:
            self.errorOccurred.emit(f"Invalid view mode: {mode}")

    @Slot(int)
    def goToPage(self, page_number: int) -> None:  # noqa: N802
        """Navigate to a specific page.

        Args:
            page_number: Target page number (0-indexed).
        """
        actual = self._backend.go_to_page(page_number)
        self._backend.pre_render_adjacent(actual)
        self.pageChanged.emit(actual)

    @Slot(str)
    def search(self, query: str) -> None:  # noqa: N802
        """Search for text in the document.

        Args:
            query: The text to search for.
        """
        if not query:
            self._search_navigator.set_matches([])
            self.searchResultsChanged.emit(0)
            self.currentMatchChanged.emit(-1)
            return

        matches = self._backend.search_text(query)
        self._search_navigator.set_matches(matches)
        self.searchResultsChanged.emit(len(matches))

        if matches:
            # Navigate to first match
            first = self._search_navigator.current_match
            if first:
                self._backend.go_to_page(first.page_number)
                self.pageChanged.emit(first.page_number)
            self.currentMatchChanged.emit(0)
        else:
            self.currentMatchChanged.emit(-1)

    @Slot()
    def nextMatch(self) -> None:  # noqa: N802
        """Navigate to the next search match."""
        match = self._search_navigator.next_match()
        if match:
            self._backend.go_to_page(match.page_number)
            self.pageChanged.emit(match.page_number)
            self.currentMatchChanged.emit(self._search_navigator.current_index)

    @Slot()
    def prevMatch(self) -> None:  # noqa: N802
        """Navigate to the previous search match."""
        match = self._search_navigator.previous_match()
        if match:
            self._backend.go_to_page(match.page_number)
            self.pageChanged.emit(match.page_number)
            self.currentMatchChanged.emit(self._search_navigator.current_index)

    @Slot(float, float)
    def setViewport(self, width: float, height: float) -> None:  # noqa: N802
        """Set the viewport dimensions for fit calculations.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self._backend.set_viewport(width, height)
