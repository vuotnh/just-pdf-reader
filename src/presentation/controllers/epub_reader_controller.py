"""EPUB Reader QML controller bridging EPUBReaderBackend and WebEngineBridge to QML views.

Provides a QObject-based controller with signals, slots, and properties
for EPUB rendering, navigation, font/theme customization, search, and bookmarks.
Integrates with the WebEngineBridge for JavaScript-based content interaction.

Requirements: 3.1–3.10, 14.1
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

from src.infrastructure.readers.epub_reader_backend import (
    EPUBReaderBackend,
    EPUBViewMode,
    FontSettings,
    SearchResult,
    TocEntry,
    clamp_font_size,
    flatten_toc,
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
)
from src.infrastructure.readers.webengine_bridge import (
    ReadingPositionState,
    WebEngineBridge,
)


class EPUBTocListModel(QAbstractListModel):
    """QAbstractListModel exposing EPUB TOC entries to QML.

    Flattens the hierarchical TOC into a linear list with indentation level.

    Roles:
        TitleRole - the section/chapter title
        HrefRole - the navigation href within the EPUB
        LevelRole - nesting level (0-based)
        ChapterIndexRole - resolved spine chapter index (-1 if unresolved)
    """

    TitleRole = Qt.ItemDataRole.UserRole + 1
    HrefRole = Qt.ItemDataRole.UserRole + 2
    LevelRole = Qt.ItemDataRole.UserRole + 3
    ChapterIndexRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[dict] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None

        entry = self._entries[index.row()]

        if role == self.TitleRole:
            return entry["title"]
        elif role == self.HrefRole:
            return entry["href"]
        elif role == self.LevelRole:
            return entry["level"]
        elif role == self.ChapterIndexRole:
            return entry["chapter_index"]
        elif role == Qt.ItemDataRole.DisplayRole:
            return entry["title"]

        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.HrefRole: b"href",
            self.LevelRole: b"level",
            self.ChapterIndexRole: b"chapterIndex",
        }

    def set_entries(
        self, entries: list[TocEntry], backend: EPUBReaderBackend | None = None
    ) -> None:
        """Replace TOC entries and notify views.

        Flattens the hierarchical TOC and resolves chapter indices from hrefs.

        Args:
            entries: Hierarchical list of TocEntry objects.
            backend: Optional backend for resolving href to chapter index.
        """
        self.beginResetModel()
        self._entries = self._flatten_with_levels(entries, backend)
        self.endResetModel()

    def get_entries(self) -> list[dict]:
        """Return the current list of flattened TOC entries."""
        return list(self._entries)

    @staticmethod
    def _flatten_with_levels(
        entries: list[TocEntry],
        backend: EPUBReaderBackend | None = None,
        level: int = 0,
    ) -> list[dict]:
        """Flatten TOC entries with level info and resolved chapter indices."""
        result: list[dict] = []
        for entry in entries:
            chapter_index = -1
            if backend is not None:
                chapter_index = _resolve_toc_href_to_chapter(
                    entry.href, backend
                )
            result.append(
                {
                    "title": entry.title,
                    "href": entry.href,
                    "level": level,
                    "chapter_index": chapter_index,
                }
            )
            if entry.children:
                result.extend(
                    EPUBTocListModel._flatten_with_levels(
                        entry.children, backend, level + 1
                    )
                )
        return result


class EPUBSearchResultModel(QAbstractListModel):
    """QAbstractListModel exposing EPUB search results to QML.

    Roles:
        ChapterIndexRole - chapter where the match was found
        MatchTextRole - matched text with context
        OffsetRole - character offset within the chapter
    """

    ChapterIndexRole = Qt.ItemDataRole.UserRole + 1
    MatchTextRole = Qt.ItemDataRole.UserRole + 2
    OffsetRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._results: list[SearchResult] = []
        self._current_index: int = -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._results)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._results):
            return None

        result = self._results[index.row()]

        if role == self.ChapterIndexRole:
            return result.chapter_index
        elif role == self.MatchTextRole:
            return result.match_text
        elif role == self.OffsetRole:
            return result.offset
        elif role == Qt.ItemDataRole.DisplayRole:
            return result.match_text

        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.ChapterIndexRole: b"chapterIndex",
            self.MatchTextRole: b"matchText",
            self.OffsetRole: b"offset",
        }

    def set_results(self, results: list[SearchResult]) -> None:
        """Replace search results and reset current index."""
        self.beginResetModel()
        self._results = list(results)
        self._current_index = 0 if results else -1
        self.endResetModel()

    def get_results(self) -> list[SearchResult]:
        """Return the current list of search results."""
        return list(self._results)

    @property
    def match_count(self) -> int:
        """Total number of search matches."""
        return len(self._results)

    @property
    def current_index(self) -> int:
        """Current match index (-1 if no results)."""
        return self._current_index

    @current_index.setter
    def current_index(self, value: int) -> None:
        """Set the current match index."""
        if self._results:
            self._current_index = max(0, min(value, len(self._results) - 1))
        else:
            self._current_index = -1

    @property
    def current_result(self) -> SearchResult | None:
        """The current search result, or None."""
        if 0 <= self._current_index < len(self._results):
            return self._results[self._current_index]
        return None

    def next_match(self) -> SearchResult | None:
        """Advance to the next match and return it."""
        if not self._results:
            return None
        self._current_index = (self._current_index + 1) % len(self._results)
        return self._results[self._current_index]

    def previous_match(self) -> SearchResult | None:
        """Go to the previous match and return it."""
        if not self._results:
            return None
        self._current_index = (self._current_index - 1) % len(self._results)
        return self._results[self._current_index]


class EPUBReaderController(QObject):
    """QObject controller bridging EPUBReaderBackend and WebEngineBridge to QML.

    Exposes EPUB reader operations as slots callable from QML and emits
    signals to notify the UI of state changes. Manages the backend,
    WebEngine bridge, search results, and TOC model.

    Requirements: 3.1–3.10, 14.1
    """

    # Signals
    documentOpened = Signal()
    documentClosed = Signal()
    chapterChanged = Signal(int)  # new chapter index (0-based)
    chapterCountChanged = Signal(int)
    viewModeChanged = Signal(str)  # "paginated" or "continuous_scroll"
    fontSettingsChanged = Signal()
    darkModeChanged = Signal(bool)
    searchResultsChanged = Signal(int)  # total match count
    currentMatchChanged = Signal(int)  # current match index
    bookmarkAdded = Signal(str)  # bookmark label
    errorOccurred = Signal(str)  # error message
    contentReady = Signal(str)  # HTML content for WebEngineView

    def __init__(
        self,
        backend: EPUBReaderBackend | None = None,
        bridge: WebEngineBridge | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend or EPUBReaderBackend()
        self._bridge = bridge or WebEngineBridge(self)
        self._toc_model = EPUBTocListModel(self)
        self._search_model = EPUBSearchResultModel(self)
        self._bookmarks: list[dict] = []

        # Connect bridge signals
        self._bridge.scrollPositionChanged.connect(self._on_scroll_changed)

    # ------------------------------------------------------------------
    # Properties (read-only, notified by signals)
    # ------------------------------------------------------------------

    @Property(int, notify=chapterChanged)
    def currentChapter(self) -> int:  # noqa: N802
        """Current chapter index (0-based)."""
        return self._backend.current_chapter

    @Property(int, notify=chapterCountChanged)
    def chapterCount(self) -> int:  # noqa: N802
        """Total number of chapters in the EPUB."""
        return self._backend.chapter_count

    @Property(str, notify=viewModeChanged)
    def viewMode(self) -> str:  # noqa: N802
        """Current view mode as a string."""
        return self._backend.view_mode.value

    @Property(str, notify=fontSettingsChanged)
    def fontFamily(self) -> str:  # noqa: N802
        """Current font family."""
        return self._backend.font_settings.family

    @Property(int, notify=fontSettingsChanged)
    def fontSize(self) -> int:  # noqa: N802
        """Current font size in pt."""
        return self._backend.font_settings.size

    @Property(float, notify=fontSettingsChanged)
    def lineHeight(self) -> float:  # noqa: N802
        """Current line height multiplier."""
        return self._backend.font_settings.line_height

    @Property(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:  # noqa: N802
        """Whether dark mode is enabled."""
        return self._backend.dark_mode

    @Property(int, notify=searchResultsChanged)
    def searchMatchCount(self) -> int:  # noqa: N802
        """Total number of search matches."""
        return self._search_model.match_count

    @Property(int, notify=currentMatchChanged)
    def currentMatchIndex(self) -> int:  # noqa: N802
        """Index of the current search match (-1 if none)."""
        return self._search_model.current_index

    @Property(QObject, constant=True)
    def tocModel(self) -> EPUBTocListModel:  # noqa: N802
        """The TOC list model for QML binding."""
        return self._toc_model

    @Property(QObject, constant=True)
    def searchModel(self) -> EPUBSearchResultModel:  # noqa: N802
        """The search results model for QML binding."""
        return self._search_model

    # ------------------------------------------------------------------
    # Public accessors (non-QML)
    # ------------------------------------------------------------------

    @property
    def backend(self) -> EPUBReaderBackend:
        """The underlying EPUB reader backend."""
        return self._backend

    @property
    def bridge(self) -> WebEngineBridge:
        """The WebEngine bridge for JS communication."""
        return self._bridge

    @property
    def bookmarks(self) -> list[dict]:
        """Current list of bookmarks for this document."""
        return list(self._bookmarks)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def openEpub(self, file_path: str) -> None:  # noqa: N802
        """Open an EPUB document.

        Parses the EPUB structure, loads the TOC, and emits contentReady
        with the first chapter's HTML for the WebEngineView.

        Args:
            file_path: Path to the EPUB file.
        """
        try:
            self._backend.open(file_path)
            # Load table of contents
            toc_entries = self._backend.toc
            self._toc_model.set_entries(toc_entries, self._backend)
            # Reset search and bookmarks
            self._search_model.set_results([])
            self._bookmarks = []
            # Emit signals
            self.chapterCountChanged.emit(self._backend.chapter_count)
            self.chapterChanged.emit(self._backend.current_chapter)
            self.viewModeChanged.emit(self._backend.view_mode.value)
            self.documentOpened.emit()
            # Load first chapter content
            self._load_current_chapter()
        except (RuntimeError, FileNotFoundError) as e:
            self.errorOccurred.emit(str(e))

    @Slot()
    def closeEpub(self) -> None:  # noqa: N802
        """Close the current EPUB document."""
        self._backend.close()
        self._toc_model.set_entries([])
        self._search_model.set_results([])
        self._bookmarks = []
        self.documentClosed.emit()
        self.chapterCountChanged.emit(0)

    @Slot(int)
    def goToChapter(self, chapter_index: int) -> None:  # noqa: N802
        """Navigate to a specific chapter.

        Args:
            chapter_index: Target chapter index (0-based).
        """
        actual = self._backend.go_to_chapter(chapter_index)
        self._bridge.set_chapter_index(actual)
        self.chapterChanged.emit(actual)
        self._load_current_chapter()

    @Slot()
    def nextChapter(self) -> None:  # noqa: N802
        """Navigate to the next chapter."""
        current = self._backend.current_chapter
        if current < self._backend.chapter_count - 1:
            self.goToChapter(current + 1)

    @Slot()
    def previousChapter(self) -> None:  # noqa: N802
        """Navigate to the previous chapter."""
        current = self._backend.current_chapter
        if current > 0:
            self.goToChapter(current - 1)

    @Slot(str, int, float)
    def setFont(self, family: str, size: int, line_height: float) -> None:  # noqa: N802
        """Set font settings for EPUB rendering.

        Font size is clamped to [8, 48] pt range.

        Args:
            family: Font family name (e.g., "serif", "sans-serif", "Georgia").
            size: Font size in points.
            line_height: Line height multiplier (e.g., 1.5).
        """
        settings = FontSettings(
            family=family,
            size=clamp_font_size(size),
            line_height=max(1.0, min(3.0, line_height)),
        )
        self._backend.set_font_settings(settings)
        self._bridge.apply_font_settings(settings)
        self.fontSettingsChanged.emit()

    @Slot(bool)
    def setTheme(self, dark_mode: bool) -> None:  # noqa: N802
        """Set the reader theme (light/dark mode).

        Dark mode inverts content colors while preserving image appearance.

        Args:
            dark_mode: True for dark mode, False for light mode.
        """
        self._backend.set_dark_mode(dark_mode)
        self._bridge.apply_dark_mode(dark_mode)
        self.darkModeChanged.emit(dark_mode)

    @Slot(str)
    def setPageMode(self, mode: str) -> None:  # noqa: N802
        """Set the page viewing mode.

        Args:
            mode: "paginated" or "continuous_scroll".
        """
        try:
            view_mode = EPUBViewMode(mode)
            self._backend.set_view_mode(view_mode)
            self.viewModeChanged.emit(mode)
            # Reload chapter with new mode CSS
            self._load_current_chapter()
        except ValueError:
            self.errorOccurred.emit(f"Invalid view mode: {mode}")

    @Slot(str)
    def search(self, query: str) -> None:  # noqa: N802
        """Search for text across all chapters in the EPUB.

        Args:
            query: The text to search for.
        """
        if not query or not query.strip():
            self._search_model.set_results([])
            self.searchResultsChanged.emit(0)
            self.currentMatchChanged.emit(-1)
            return

        try:
            results = self._backend.search_text(query)
            self._search_model.set_results(results)
            self.searchResultsChanged.emit(len(results))

            if results:
                # Navigate to first match
                first = results[0]
                if first.chapter_index != self._backend.current_chapter:
                    self.goToChapter(first.chapter_index)
                self.currentMatchChanged.emit(0)
            else:
                self.currentMatchChanged.emit(-1)
        except RuntimeError as e:
            self.errorOccurred.emit(str(e))

    @Slot()
    def nextMatch(self) -> None:  # noqa: N802
        """Navigate to the next search match."""
        result = self._search_model.next_match()
        if result:
            if result.chapter_index != self._backend.current_chapter:
                self.goToChapter(result.chapter_index)
            self.currentMatchChanged.emit(self._search_model.current_index)

    @Slot()
    def prevMatch(self) -> None:  # noqa: N802
        """Navigate to the previous search match."""
        result = self._search_model.previous_match()
        if result:
            if result.chapter_index != self._backend.current_chapter:
                self.goToChapter(result.chapter_index)
            self.currentMatchChanged.emit(self._search_model.current_index)

    @Slot(str)
    def addBookmark(self, label: str = "") -> None:  # noqa: N802
        """Add a bookmark at the current reading position.

        Persists the bookmark with chapter reference and scroll offset.

        Args:
            label: Optional label for the bookmark.
        """
        position = self._bridge.get_reading_position()
        bookmark = {
            "chapter_index": position.chapter_index,
            "scroll_offset": position.scroll_offset,
            "label": label or f"Chapter {position.chapter_index + 1}",
        }
        self._bookmarks.append(bookmark)
        self.bookmarkAdded.emit(bookmark["label"])

    @Slot(float, float)
    def setViewport(self, width: float, height: float) -> None:  # noqa: N802
        """Set the viewport dimensions for pagination.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self._backend.set_viewport(int(width), int(height))

    @Slot(result=str)
    def getCurrentHtml(self) -> str:  # noqa: N802
        """Get the HTML content of the current chapter.

        Returns:
            HTML string for rendering in WebEngineView.
        """
        try:
            return self._backend.get_chapter_html()
        except (RuntimeError, IndexError):
            return ""

    @Slot(int, float)
    def restorePosition(self, chapter_index: int, scroll_offset: float) -> None:  # noqa: N802
        """Restore a previously saved reading position.

        Args:
            chapter_index: Chapter index to navigate to.
            scroll_offset: Scroll offset fraction [0.0, 1.0].
        """
        self.goToChapter(chapter_index)
        position = ReadingPositionState(
            chapter_index=chapter_index,
            scroll_offset=scroll_offset,
        )
        self._bridge.restore_reading_position(position)

    @Slot(result=int)
    def getPositionChapter(self) -> int:  # noqa: N802
        """Get the chapter index of the current reading position.

        Returns:
            Current chapter index.
        """
        return self._bridge.get_reading_position().chapter_index

    @Slot(result=float)
    def getPositionOffset(self) -> float:  # noqa: N802
        """Get the scroll offset of the current reading position.

        Returns:
            Current scroll offset as fraction [0.0, 1.0].
        """
        return self._bridge.get_reading_position().scroll_offset

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_current_chapter(self) -> None:
        """Load the current chapter's HTML and emit contentReady signal."""
        try:
            html_content = self._backend.get_chapter_html()
            self.contentReady.emit(html_content)
        except (RuntimeError, IndexError) as e:
            self.errorOccurred.emit(f"Failed to load chapter: {e}")

    def _on_scroll_changed(self, position: float) -> None:
        """Handle scroll position changes from the bridge.

        Args:
            position: New scroll position as fraction [0.0, 1.0].
        """
        # The bridge already tracks the position internally
        pass


def _resolve_toc_href_to_chapter(
    href: str, backend: EPUBReaderBackend
) -> int:
    """Resolve a TOC href to a spine chapter index.

    The href may contain a fragment (e.g., "chapter1.xhtml#section2").
    We match the file part against spine item hrefs.

    Args:
        href: The TOC entry href (relative path, possibly with fragment).
        backend: The EPUB backend with spine information.

    Returns:
        The chapter index (0-based), or -1 if not resolved.
    """
    if not href:
        return -1

    # Strip fragment identifier
    file_part = href.split("#")[0] if "#" in href else href

    for idx, spine_item in enumerate(backend.spine):
        if spine_item.href == file_part or spine_item.href.endswith(file_part):
            return idx

    return -1
