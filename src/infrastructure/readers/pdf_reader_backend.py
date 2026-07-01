"""PDF Reader Backend using PyMuPDF (fitz).

Provides page rendering, caching, zoom management, view modes,
and text extraction for PDF documents.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import fitz  # PyMuPDF


class ViewMode(Enum):
    """PDF viewing modes."""

    SINGLE_PAGE = "single_page"
    CONTINUOUS_SCROLL = "continuous_scroll"


class ZoomPreset(Enum):
    """Predefined zoom presets."""

    FIT_WIDTH = "fit_width"
    FIT_PAGE = "fit_page"
    CUSTOM = "custom"


# Zoom constraints
MIN_ZOOM = 0.25  # 25%
MAX_ZOOM = 4.0  # 400%
DEFAULT_ZOOM = 1.0  # 100%

# Cache configuration
DEFAULT_CACHE_SIZE = 20
PRE_RENDER_RANGE = 3  # ±3 adjacent pages


@dataclass
class RenderedPage:
    """A rendered page with its pixel data and metadata."""

    page_number: int
    width: int
    height: int
    pixel_data: bytes
    zoom_level: float
    samples: int = 3  # RGB by default


@dataclass
class TocEntry:
    """A table of contents entry from the PDF outline."""

    level: int
    title: str
    page_number: int  # 0-indexed page number


@dataclass
class SearchMatch:
    """A text search match with position information."""

    page_number: int  # 0-indexed
    text: str  # The matched text
    rect: tuple[float, float, float, float]  # (x0, y0, x1, y1) bounding box


@dataclass
class TextBlock:
    """A block of extracted text with position info."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    block_number: int
    line_number: int
    span_number: int
    font: str = ""
    size: float = 0.0
    flags: int = 0


@dataclass
class PageTextContent:
    """Full text extraction result for a page."""

    page_number: int
    blocks: list[TextBlock] = field(default_factory=list)
    raw_dict: dict[str, Any] = field(default_factory=dict)


def clamp_zoom(zoom: float) -> float:
    """Clamp a zoom level to the valid range [MIN_ZOOM, MAX_ZOOM].

    Args:
        zoom: The requested zoom level as a multiplier (e.g. 1.0 = 100%).

    Returns:
        The clamped zoom level, guaranteed within [0.25, 4.0].
    """
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


class PageCache:
    """Thread-safe LRU cache for rendered pages.

    Caches rendered page data keyed by (page_number, zoom_level) tuples.
    Uses an OrderedDict to maintain LRU ordering.
    """

    def __init__(self, max_size: int = DEFAULT_CACHE_SIZE) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[tuple[int, float], RenderedPage] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def max_size(self) -> int:
        """Maximum number of pages in the cache."""
        return self._max_size

    def get(self, page_number: int, zoom_level: float) -> RenderedPage | None:
        """Retrieve a cached page, moving it to most-recently-used position.

        Args:
            page_number: The page number (0-indexed).
            zoom_level: The zoom level the page was rendered at.

        Returns:
            The cached RenderedPage, or None if not in cache.
        """
        key = (page_number, zoom_level)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def put(self, page: RenderedPage) -> None:
        """Add a rendered page to the cache, evicting LRU if full.

        Args:
            page: The rendered page to cache.
        """
        key = (page.page_number, page.zoom_level)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = page
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)  # Evict LRU
                self._cache[key] = page

    def invalidate(self, page_number: int | None = None) -> None:
        """Invalidate cached pages.

        Args:
            page_number: If provided, invalidate only entries for this page.
                        If None, clear the entire cache.
        """
        with self._lock:
            if page_number is None:
                self._cache.clear()
            else:
                keys_to_remove = [
                    k for k in self._cache if k[0] == page_number
                ]
                for key in keys_to_remove:
                    del self._cache[key]

    def __len__(self) -> int:
        """Return the current number of cached pages."""
        with self._lock:
            return len(self._cache)

    def contains(self, page_number: int, zoom_level: float) -> bool:
        """Check if a page is in the cache without affecting LRU order."""
        key = (page_number, zoom_level)
        with self._lock:
            return key in self._cache


class PDFReaderBackend:
    """Backend for reading and rendering PDF documents using PyMuPDF.

    Provides:
    - Page rendering to pixel data (bytes) at arbitrary zoom levels
    - LRU page cache (default 20 pages) with pre-rendering of adjacent pages
    - Zoom level clamping (25% to 400%) with fit-width and fit-page presets
    - Continuous scroll mode and single-page mode
    - Text extraction via page.get_text("dict") for selection support
    """

    def __init__(
        self,
        file_path: str | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        """Initialize the PDF reader backend.

        Args:
            file_path: Path to the PDF file to open. Can be None for deferred open.
            cache_size: Maximum number of pages to keep in the LRU cache.
        """
        self._doc: fitz.Document | None = None
        self._file_path: str | None = file_path
        self._cache = PageCache(max_size=cache_size)
        self._zoom_level: float = DEFAULT_ZOOM
        self._zoom_preset: ZoomPreset = ZoomPreset.CUSTOM
        self._view_mode: ViewMode = ViewMode.CONTINUOUS_SCROLL
        self._current_page: int = 0
        self._viewport_width: float = 800.0  # Default viewport width in pixels
        self._viewport_height: float = 600.0  # Default viewport height in pixels

        if file_path:
            self.open(file_path)

    @property
    def document(self) -> fitz.Document | None:
        """The underlying PyMuPDF document."""
        return self._doc

    @property
    def page_count(self) -> int:
        """Total number of pages in the document."""
        if self._doc is None:
            return 0
        return self._doc.page_count

    @property
    def zoom_level(self) -> float:
        """Current zoom level as a multiplier (e.g. 1.0 = 100%)."""
        return self._zoom_level

    @property
    def zoom_preset(self) -> ZoomPreset:
        """Current zoom preset."""
        return self._zoom_preset

    @property
    def view_mode(self) -> ViewMode:
        """Current view mode (single page or continuous scroll)."""
        return self._view_mode

    @property
    def current_page(self) -> int:
        """Current page number (0-indexed)."""
        return self._current_page

    @property
    def cache(self) -> PageCache:
        """The page cache instance."""
        return self._cache

    def open(self, file_path: str) -> None:
        """Open a PDF document.

        Args:
            file_path: Path to the PDF file.

        Raises:
            FileNotFoundError: If the file does not exist.
            RuntimeError: If the file cannot be opened as a PDF.
        """
        try:
            self._doc = fitz.open(file_path)
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}") from e
        self._file_path = file_path
        self._current_page = 0
        self._cache.invalidate()

    def close(self) -> None:
        """Close the document and release resources."""
        if self._doc:
            self._doc.close()
            self._doc = None
        self._cache.invalidate()
        self._file_path = None
        self._current_page = 0

    def set_viewport(self, width: float, height: float) -> None:
        """Set the viewport dimensions for fit-width and fit-page calculations.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self._viewport_width = max(1.0, width)
        self._viewport_height = max(1.0, height)

    def set_zoom(self, zoom: float) -> float:
        """Set the zoom level, clamping to valid range.

        Args:
            zoom: Requested zoom level as a multiplier.

        Returns:
            The actual zoom level after clamping.
        """
        self._zoom_level = clamp_zoom(zoom)
        self._zoom_preset = ZoomPreset.CUSTOM
        return self._zoom_level

    def set_zoom_fit_width(self) -> float:
        """Set zoom to fit the page width within the viewport.

        Returns:
            The calculated zoom level.
        """
        if self._doc is None or self._doc.page_count == 0:
            return self._zoom_level

        page = self._doc[self._current_page]
        page_width = page.rect.width
        if page_width <= 0:
            return self._zoom_level

        zoom = self._viewport_width / page_width
        self._zoom_level = clamp_zoom(zoom)
        self._zoom_preset = ZoomPreset.FIT_WIDTH
        return self._zoom_level

    def set_zoom_fit_page(self) -> float:
        """Set zoom to fit the entire page within the viewport.

        Returns:
            The calculated zoom level.
        """
        if self._doc is None or self._doc.page_count == 0:
            return self._zoom_level

        page = self._doc[self._current_page]
        page_width = page.rect.width
        page_height = page.rect.height
        if page_width <= 0 or page_height <= 0:
            return self._zoom_level

        zoom_w = self._viewport_width / page_width
        zoom_h = self._viewport_height / page_height
        zoom = min(zoom_w, zoom_h)
        self._zoom_level = clamp_zoom(zoom)
        self._zoom_preset = ZoomPreset.FIT_PAGE
        return self._zoom_level

    def set_view_mode(self, mode: ViewMode) -> None:
        """Set the view mode.

        Args:
            mode: The desired view mode.
        """
        self._view_mode = mode

    def go_to_page(self, page_number: int) -> int:
        """Navigate to a specific page.

        Args:
            page_number: Target page number (0-indexed).

        Returns:
            The actual page number navigated to (clamped to valid range).
        """
        if self._doc is None:
            return 0
        self._current_page = max(0, min(page_number, self._doc.page_count - 1))
        return self._current_page

    def render_page(self, page_number: int, zoom: float | None = None) -> RenderedPage:
        """Render a page at the specified zoom level.

        First checks the cache; if not found, renders via PyMuPDF and caches.

        Args:
            page_number: The page to render (0-indexed).
            zoom: Zoom level override. If None, uses current zoom level.

        Returns:
            A RenderedPage containing the pixel data.

        Raises:
            RuntimeError: If no document is open.
            IndexError: If page_number is out of range.
        """
        if self._doc is None:
            raise RuntimeError("No document is open")
        if page_number < 0 or page_number >= self._doc.page_count:
            raise IndexError(
                f"Page {page_number} out of range [0, {self._doc.page_count - 1}]"
            )

        effective_zoom = clamp_zoom(zoom if zoom is not None else self._zoom_level)

        # Check cache first
        cached = self._cache.get(page_number, effective_zoom)
        if cached is not None:
            return cached

        # Render the page
        rendered = self._render_page_internal(page_number, effective_zoom)
        self._cache.put(rendered)
        return rendered

    def pre_render_adjacent(self, center_page: int, zoom: float | None = None) -> None:
        """Pre-render pages adjacent to the center page for smooth scrolling.

        Pre-renders ±PRE_RENDER_RANGE pages around the center page that
        are not already cached.

        Args:
            center_page: The current/center page number.
            zoom: Zoom level to render at. If None, uses current zoom level.
        """
        if self._doc is None:
            return

        effective_zoom = clamp_zoom(zoom if zoom is not None else self._zoom_level)
        start = max(0, center_page - PRE_RENDER_RANGE)
        end = min(self._doc.page_count - 1, center_page + PRE_RENDER_RANGE)

        for page_num in range(start, end + 1):
            if not self._cache.contains(page_num, effective_zoom):
                rendered = self._render_page_internal(page_num, effective_zoom)
                self._cache.put(rendered)

    def extract_text(self, page_number: int) -> PageTextContent:
        """Extract text content from a page with position information.

        Uses page.get_text("dict") for detailed text block extraction,
        suitable for text selection and search.

        Args:
            page_number: The page to extract text from (0-indexed).

        Returns:
            PageTextContent with all text blocks and their positions.

        Raises:
            RuntimeError: If no document is open.
            IndexError: If page_number is out of range.
        """
        if self._doc is None:
            raise RuntimeError("No document is open")
        if page_number < 0 or page_number >= self._doc.page_count:
            raise IndexError(
                f"Page {page_number} out of range [0, {self._doc.page_count - 1}]"
            )

        page = self._doc[page_number]
        text_dict = page.get_text("dict")

        blocks: list[TextBlock] = []
        block_num = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # Skip image blocks
                continue
            for line_num, line in enumerate(block.get("lines", [])):
                for span_num, span in enumerate(line.get("spans", [])):
                    blocks.append(
                        TextBlock(
                            text=span.get("text", ""),
                            x0=span.get("bbox", [0, 0, 0, 0])[0],
                            y0=span.get("bbox", [0, 0, 0, 0])[1],
                            x1=span.get("bbox", [0, 0, 0, 0])[2],
                            y1=span.get("bbox", [0, 0, 0, 0])[3],
                            block_number=block_num,
                            line_number=line_num,
                            span_number=span_num,
                            font=span.get("font", ""),
                            size=span.get("size", 0.0),
                            flags=span.get("flags", 0),
                        )
                    )
            block_num += 1

        return PageTextContent(
            page_number=page_number,
            blocks=blocks,
            raw_dict=text_dict,
        )

    def get_page_size(self, page_number: int) -> tuple[float, float]:
        """Get the native page size (before zoom) in points.

        Args:
            page_number: The page number (0-indexed).

        Returns:
            Tuple of (width, height) in points.

        Raises:
            RuntimeError: If no document is open.
            IndexError: If page_number is out of range.
        """
        if self._doc is None:
            raise RuntimeError("No document is open")
        if page_number < 0 or page_number >= self._doc.page_count:
            raise IndexError(
                f"Page {page_number} out of range [0, {self._doc.page_count - 1}]"
            )
        page = self._doc[page_number]
        return (page.rect.width, page.rect.height)

    def get_visible_pages(self, scroll_offset: float = 0.0) -> list[int]:
        """Determine which pages are visible given the current viewport and scroll.

        In single-page mode, returns only the current page.
        In continuous scroll mode, returns all pages visible in the viewport.

        Args:
            scroll_offset: The current vertical scroll offset in pixels.

        Returns:
            List of visible page numbers (0-indexed).
        """
        if self._doc is None:
            return []

        if self._view_mode == ViewMode.SINGLE_PAGE:
            return [self._current_page]

        # Continuous scroll: calculate visible pages based on accumulated heights
        visible = []
        accumulated_height = 0.0
        viewport_top = scroll_offset
        viewport_bottom = scroll_offset + self._viewport_height

        for i in range(self._doc.page_count):
            page = self._doc[i]
            page_height = page.rect.height * self._zoom_level
            page_top = accumulated_height
            page_bottom = accumulated_height + page_height

            # Check if page overlaps with viewport
            if page_bottom > viewport_top and page_top < viewport_bottom:
                visible.append(i)
            elif page_top >= viewport_bottom:
                break  # No more pages can be visible

            accumulated_height = page_bottom

        return visible

    def get_toc(self) -> list[TocEntry]:
        """Extract the table of contents from the PDF document outline.

        Uses PyMuPDF's doc.get_toc() to retrieve the document outline.
        Each TOC entry contains the nesting level, title, and target page.

        Returns:
            List of TocEntry objects representing the document outline.
            Returns an empty list if no outline exists or no document is open.
        """
        if self._doc is None:
            return []

        toc_raw = self._doc.get_toc()
        entries: list[TocEntry] = []
        for item in toc_raw:
            # get_toc() returns list of [level, title, page_number]
            # page_number is 1-indexed in PyMuPDF's get_toc; convert to 0-indexed
            level = item[0]
            title = item[1]
            page_num = max(0, item[2] - 1)  # Convert to 0-indexed, clamp to 0
            entries.append(TocEntry(level=level, title=title, page_number=page_num))

        return entries

    def search_text(self, query: str, case_sensitive: bool = False) -> list[SearchMatch]:
        """Search for text across all pages of the document.

        Searches each page for occurrences of the query string and returns
        all matches with their page numbers and bounding rectangles.

        Args:
            query: The text to search for.
            case_sensitive: Whether the search is case-sensitive. Defaults to False.

        Returns:
            List of SearchMatch objects with page numbers and positions.
            Returns an empty list if no document is open or query is empty.
        """
        if self._doc is None or not query:
            return []

        matches: list[SearchMatch] = []
        flags = 0 if case_sensitive else fitz.TEXT_PRESERVE_WHITESPACE

        for page_num in range(self._doc.page_count):
            page = self._doc[page_num]
            # search_for returns a list of fitz.Rect objects
            rects = page.search_for(query, flags=flags)
            for rect in rects:
                matches.append(
                    SearchMatch(
                        page_number=page_num,
                        text=query,
                        rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    )
                )

        return matches

    def _render_page_internal(self, page_number: int, zoom: float) -> RenderedPage:
        """Internal method to render a page using PyMuPDF.

        Args:
            page_number: The page to render (0-indexed).
            zoom: The zoom level to apply.

        Returns:
            A RenderedPage with the pixel data.
        """
        page = self._doc[page_number]
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)

        return RenderedPage(
            page_number=page_number,
            width=pixmap.width,
            height=pixmap.height,
            pixel_data=pixmap.samples,
            zoom_level=zoom,
            samples=pixmap.n,
        )


class SearchNavigator:
    """Manages navigation between search results (next/previous match).

    Provides stateful navigation through a list of search matches,
    tracking the current match index and supporting wrap-around.
    """

    def __init__(self, matches: list[SearchMatch] | None = None) -> None:
        """Initialize the navigator with optional initial matches.

        Args:
            matches: Initial list of search matches. Defaults to empty list.
        """
        self._matches: list[SearchMatch] = matches or []
        self._current_index: int = -1 if not matches else 0

    @property
    def matches(self) -> list[SearchMatch]:
        """All search matches."""
        return self._matches

    @property
    def current_index(self) -> int:
        """Index of the current match (-1 if no matches)."""
        return self._current_index

    @property
    def current_match(self) -> SearchMatch | None:
        """The current search match, or None if no matches exist."""
        if not self._matches or self._current_index < 0:
            return None
        return self._matches[self._current_index]

    @property
    def match_count(self) -> int:
        """Total number of matches."""
        return len(self._matches)

    def set_matches(self, matches: list[SearchMatch]) -> None:
        """Replace the current matches and reset navigation to the first match.

        Args:
            matches: The new list of search matches.
        """
        self._matches = matches
        self._current_index = 0 if matches else -1

    def next_match(self) -> SearchMatch | None:
        """Navigate to the next match, wrapping around to the first.

        Returns:
            The next SearchMatch, or None if no matches exist.
        """
        if not self._matches:
            return None
        self._current_index = (self._current_index + 1) % len(self._matches)
        return self._matches[self._current_index]

    def previous_match(self) -> SearchMatch | None:
        """Navigate to the previous match, wrapping around to the last.

        Returns:
            The previous SearchMatch, or None if no matches exist.
        """
        if not self._matches:
            return None
        self._current_index = (self._current_index - 1) % len(self._matches)
        return self._matches[self._current_index]

    def go_to_match(self, index: int) -> SearchMatch | None:
        """Navigate to a specific match by index.

        Args:
            index: The match index to navigate to (0-based).

        Returns:
            The SearchMatch at the given index, or None if index is invalid.
        """
        if not self._matches or index < 0 or index >= len(self._matches):
            return None
        self._current_index = index
        return self._matches[self._current_index]
