"""EPUB Reader Backend.

Parses EPUB zip structure to extract HTML chapters, CSS, and images.
Provides CSS injection for font settings, theme (dark mode), and annotation highlights.
Supports pagination mode (CSS column splitting) and continuous scroll mode.
"""

from __future__ import annotations

import html
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from src.domain.enums import HighlightColor


class EPUBViewMode(Enum):
    """EPUB viewing modes."""

    PAGINATED = "paginated"
    CONTINUOUS_SCROLL = "continuous_scroll"


# EPUB XML namespaces
NAMESPACES = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}

# Default font settings
DEFAULT_FONT_FAMILY = "serif"
DEFAULT_FONT_SIZE = 16  # pt
DEFAULT_LINE_HEIGHT = 1.5
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 48


@dataclass
class FontSettings:
    """User-configurable font settings for EPUB rendering."""

    family: str = DEFAULT_FONT_FAMILY
    size: int = DEFAULT_FONT_SIZE
    line_height: float = DEFAULT_LINE_HEIGHT


@dataclass
class TocEntry:
    """An entry in the EPUB table of contents."""

    title: str
    href: str  # Relative path within EPUB
    children: list[TocEntry] = field(default_factory=list)


@dataclass
class SpineItem:
    """An item in the EPUB reading order (spine)."""

    id: str
    href: str  # Relative path within EPUB (from OPF directory)
    media_type: str = "application/xhtml+xml"
    linear: bool = True


@dataclass
class SearchResult:
    """A search match found in an EPUB chapter."""

    chapter_index: int  # 0-based index into the spine
    match_text: str  # The matched text with surrounding context
    offset: int  # Character offset within the chapter's plain text


@dataclass
class EPUBMetadata:
    """Metadata extracted from the EPUB OPF file."""

    title: str = ""
    author: str = ""
    publisher: str = ""
    language: str = ""
    identifier: str = ""
    description: str = ""


@dataclass
class AnnotationHighlight:
    """An annotation highlight to inject as CSS."""

    annotation_id: str
    color: HighlightColor
    start_offset: int
    end_offset: int


def clamp_font_size(size: int) -> int:
    """Clamp font size to valid range [MIN_FONT_SIZE, MAX_FONT_SIZE]."""
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def generate_font_css(settings: FontSettings) -> str:
    """Generate CSS for font settings.

    Args:
        settings: The font settings to apply.

    Returns:
        CSS string with font-family, font-size, and line-height.
    """
    size = clamp_font_size(settings.size)
    return (
        f"body {{\n"
        f"  font-family: {settings.family};\n"
        f"  font-size: {size}pt;\n"
        f"  line-height: {settings.line_height};\n"
        f"}}\n"
    )


def generate_dark_mode_css() -> str:
    """Generate CSS for dark mode theme.

    Inverts content colors while preserving image appearance.

    Returns:
        CSS string for dark mode.
    """
    return (
        "body {\n"
        "  background-color: #1a1a1a;\n"
        "  color: #e0e0e0;\n"
        "}\n"
        "a {\n"
        "  color: #6db3f2;\n"
        "}\n"
        "img, svg, video {\n"
        "  filter: none;\n"
        "}\n"
    )


def generate_highlight_css(highlights: list[AnnotationHighlight]) -> str:
    """Generate CSS for annotation highlights.

    Creates CSS classes for each highlight color and specific highlight spans.

    Args:
        highlights: List of annotation highlights to render.

    Returns:
        CSS string for annotation highlight styling.
    """
    color_map = {
        HighlightColor.YELLOW: "rgba(255, 255, 0, 0.3)",
        HighlightColor.GREEN: "rgba(0, 255, 0, 0.3)",
        HighlightColor.BLUE: "rgba(0, 150, 255, 0.3)",
        HighlightColor.PINK: "rgba(255, 105, 180, 0.3)",
        HighlightColor.ORANGE: "rgba(255, 165, 0, 0.3)",
    }

    css_parts = []
    for highlight in highlights:
        bg_color = color_map.get(highlight.color, "rgba(255, 255, 0, 0.3)")
        css_parts.append(
            f".annotation-{highlight.annotation_id} {{\n"
            f"  background-color: {bg_color};\n"
            f"}}\n"
        )
    return "\n".join(css_parts)


def generate_pagination_css(
    viewport_width: int = 800, viewport_height: int = 600
) -> str:
    """Generate CSS for pagination mode using CSS columns.

    Args:
        viewport_width: Width of the reading viewport in pixels.
        viewport_height: Height of the reading viewport in pixels.

    Returns:
        CSS string for column-based pagination.
    """
    return (
        "body {\n"
        "  margin: 0;\n"
        "  padding: 20px;\n"
        "  overflow: hidden;\n"
        f"  height: {viewport_height - 40}px;\n"
        f"  column-width: {viewport_width - 40}px;\n"
        "  column-gap: 40px;\n"
        "  column-fill: auto;\n"
        "}\n"
    )


def generate_scroll_css() -> str:
    """Generate CSS for continuous scroll mode.

    Returns:
        CSS string for natural flow scrolling.
    """
    return (
        "body {\n"
        "  margin: 0;\n"
        "  padding: 20px;\n"
        "  overflow-y: auto;\n"
        "}\n"
    )


def flatten_toc(entries: list[TocEntry]) -> list[TocEntry]:
    """Flatten a nested TOC structure into a linear list for sequential navigation.

    Recursively traverses the TOC tree in depth-first order, producing a flat
    list suitable for linear next/previous navigation.

    Args:
        entries: The hierarchical list of TocEntry objects.

    Returns:
        A flat list of all TocEntry objects in reading order.
    """
    result: list[TocEntry] = []
    for entry in entries:
        result.append(entry)
        if entry.children:
            result.extend(flatten_toc(entry.children))
    return result


def _strip_html_tags(html_content: str) -> str:
    """Extract plain text from HTML content by stripping all tags.

    Args:
        html_content: Raw HTML string.

    Returns:
        Plain text with HTML tags removed and entities decoded.
    """
    # Remove script and style elements entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    # Replace block-level elements with a space to maintain word boundaries
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr|td|th|blockquote|pre)[^>]*/?>", " ", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse multiple whitespace into single spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class EPUBReaderBackend:
    """Backend for reading and rendering EPUB documents.

    Provides:
    - EPUB zip extraction and structure parsing (OPF, NCX/NAV)
    - HTML chapter extraction with resource resolution
    - CSS injection for font settings, theme (dark mode), annotation highlights
    - Pagination mode (CSS column splitting) and continuous scroll mode
    """

    def __init__(self, file_path: str | None = None) -> None:
        """Initialize the EPUB reader backend.

        Args:
            file_path: Path to the EPUB file to open. Can be None for deferred open.
        """
        self._file_path: str | None = None
        self._zip: zipfile.ZipFile | None = None
        self._opf_path: str = ""
        self._opf_dir: str = ""
        self._metadata: EPUBMetadata = EPUBMetadata()
        self._spine: list[SpineItem] = []
        self._manifest: dict[str, dict[str, str]] = {}
        self._toc: list[TocEntry] = []
        self._current_chapter: int = 0
        self._view_mode: EPUBViewMode = EPUBViewMode.CONTINUOUS_SCROLL
        self._font_settings: FontSettings = FontSettings()
        self._dark_mode: bool = False
        self._highlights: list[AnnotationHighlight] = []
        self._viewport_width: int = 800
        self._viewport_height: int = 600

        if file_path:
            self.open(file_path)

    @property
    def file_path(self) -> str | None:
        """Path to the currently open EPUB file."""
        return self._file_path

    @property
    def metadata(self) -> EPUBMetadata:
        """Metadata extracted from the EPUB."""
        return self._metadata

    @property
    def spine(self) -> list[SpineItem]:
        """Reading order of the EPUB (spine items)."""
        return self._spine

    @property
    def toc(self) -> list[TocEntry]:
        """Table of contents entries."""
        return self._toc

    @property
    def chapter_count(self) -> int:
        """Number of chapters (spine items) in the EPUB."""
        return len(self._spine)

    @property
    def current_chapter(self) -> int:
        """Current chapter index (0-based)."""
        return self._current_chapter

    @property
    def view_mode(self) -> EPUBViewMode:
        """Current view mode."""
        return self._view_mode

    @property
    def font_settings(self) -> FontSettings:
        """Current font settings."""
        return self._font_settings

    @property
    def dark_mode(self) -> bool:
        """Whether dark mode is active."""
        return self._dark_mode

    @property
    def viewport_width(self) -> int:
        """Current viewport width in pixels."""
        return self._viewport_width

    @property
    def viewport_height(self) -> int:
        """Current viewport height in pixels."""
        return self._viewport_height

    def open(self, file_path: str) -> None:
        """Open an EPUB file and parse its structure.

        Args:
            file_path: Path to the EPUB file.

        Raises:
            FileNotFoundError: If the file does not exist.
            RuntimeError: If the file is not a valid EPUB.
        """
        try:
            self._zip = zipfile.ZipFile(file_path, "r")
        except (zipfile.BadZipFile, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to open EPUB: {e}") from e

        self._file_path = file_path
        self._parse_container()
        self._parse_opf()
        self._parse_toc()
        self._current_chapter = 0

    def close(self) -> None:
        """Close the EPUB file and release resources."""
        if self._zip:
            self._zip.close()
            self._zip = None
        self._file_path = None
        self._opf_path = ""
        self._opf_dir = ""
        self._metadata = EPUBMetadata()
        self._spine = []
        self._manifest = {}
        self._toc = []
        self._current_chapter = 0

    def set_viewport(self, width: int, height: int) -> None:
        """Set the viewport dimensions for pagination.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self._viewport_width = max(100, width)
        self._viewport_height = max(100, height)

    def set_view_mode(self, mode: EPUBViewMode) -> None:
        """Set the viewing mode.

        Args:
            mode: The desired view mode.
        """
        self._view_mode = mode

    def set_font_settings(self, settings: FontSettings) -> None:
        """Update font settings.

        Args:
            settings: New font settings to apply.
        """
        self._font_settings = FontSettings(
            family=settings.family,
            size=clamp_font_size(settings.size),
            line_height=settings.line_height,
        )

    def set_dark_mode(self, enabled: bool) -> None:
        """Enable or disable dark mode.

        Args:
            enabled: Whether dark mode should be active.
        """
        self._dark_mode = enabled

    def set_highlights(self, highlights: list[AnnotationHighlight]) -> None:
        """Set the annotation highlights for CSS injection.

        Args:
            highlights: List of annotation highlights.
        """
        self._highlights = highlights

    def go_to_chapter(self, chapter_index: int) -> int:
        """Navigate to a specific chapter.

        Args:
            chapter_index: Target chapter index (0-based).

        Returns:
            The actual chapter index navigated to (clamped to valid range).
        """
        if not self._spine:
            return 0
        self._current_chapter = max(0, min(chapter_index, len(self._spine) - 1))
        return self._current_chapter

    def get_chapter_html(self, chapter_index: int | None = None) -> str:
        """Get the HTML content for a chapter with CSS injection.

        Returns the raw HTML from the EPUB with injected CSS for font
        settings, theme, highlights, and view mode.

        Args:
            chapter_index: Chapter index (0-based). If None, uses current chapter.

        Returns:
            Full HTML string with injected CSS.

        Raises:
            RuntimeError: If no EPUB is open.
            IndexError: If chapter_index is out of range.
        """
        if self._zip is None:
            raise RuntimeError("No EPUB is open")

        if not self._spine:
            raise RuntimeError("EPUB has no spine items")

        idx = chapter_index if chapter_index is not None else self._current_chapter
        if idx < 0 or idx >= len(self._spine):
            raise IndexError(
                f"Chapter {idx} out of range [0, {len(self._spine) - 1}]"
            )

        spine_item = self._spine[idx]
        # Build the full path within the zip
        chapter_path = self._resolve_path(spine_item.href)
        raw_html = self._read_zip_file(chapter_path)

        # Inject CSS into the HTML
        injected_css = self._build_injected_css()
        html_with_css = self._inject_css_into_html(raw_html, injected_css)

        return html_with_css

    def get_chapter_raw_html(self, chapter_index: int | None = None) -> str:
        """Get the raw HTML content for a chapter without CSS injection.

        Args:
            chapter_index: Chapter index (0-based). If None, uses current chapter.

        Returns:
            Raw HTML string from the EPUB.

        Raises:
            RuntimeError: If no EPUB is open.
            IndexError: If chapter_index is out of range.
        """
        if self._zip is None:
            raise RuntimeError("No EPUB is open")

        if not self._spine:
            raise RuntimeError("EPUB has no spine items")

        idx = chapter_index if chapter_index is not None else self._current_chapter
        if idx < 0 or idx >= len(self._spine):
            raise IndexError(
                f"Chapter {idx} out of range [0, {len(self._spine) - 1}]"
            )

        spine_item = self._spine[idx]
        chapter_path = self._resolve_path(spine_item.href)
        return self._read_zip_file(chapter_path)

    def get_resource(self, resource_path: str) -> bytes:
        """Get a resource (image, CSS, font) from the EPUB.

        Args:
            resource_path: Path to the resource relative to the OPF directory.

        Returns:
            The raw bytes of the resource.

        Raises:
            RuntimeError: If no EPUB is open.
            FileNotFoundError: If the resource is not found.
        """
        if self._zip is None:
            raise RuntimeError("No EPUB is open")

        full_path = self._resolve_path(resource_path)
        try:
            return self._zip.read(full_path)
        except KeyError:
            raise FileNotFoundError(
                f"Resource not found in EPUB: {resource_path}"
            )

    def resolve_resource_path(self, href: str, chapter_index: int | None = None) -> str:
        """Resolve a relative resource path from a chapter's context.

        Given an href from within a chapter HTML (e.g., ../images/fig1.png),
        resolves it to an absolute path within the EPUB zip.

        Args:
            href: Relative path from the chapter's HTML.
            chapter_index: The chapter containing the reference. Defaults to current.

        Returns:
            Absolute path within the EPUB zip.
        """
        idx = chapter_index if chapter_index is not None else self._current_chapter
        if idx < 0 or idx >= len(self._spine):
            return href

        spine_item = self._spine[idx]
        chapter_path = self._resolve_path(spine_item.href)
        chapter_dir = str(PurePosixPath(chapter_path).parent)
        resolved = posixpath.normpath(posixpath.join(chapter_dir, href))
        return resolved

    def get_manifest_items(self, media_type: str | None = None) -> list[dict[str, str]]:
        """Get manifest items, optionally filtered by media type.

        Args:
            media_type: If provided, only items with this media type are returned.

        Returns:
            List of manifest item dicts with keys: id, href, media_type.
        """
        items = []
        for item_id, item_data in self._manifest.items():
            if media_type is None or item_data.get("media-type") == media_type:
                items.append({
                    "id": item_id,
                    "href": item_data.get("href", ""),
                    "media_type": item_data.get("media-type", ""),
                })
        return items

    def search_text(self, query: str) -> list[SearchResult]:
        """Search for text across all chapters in the EPUB.

        Performs a case-insensitive search across all spine items (chapters),
        returning all matches with chapter index, matched text with context,
        and character offset within the chapter's plain text.

        Args:
            query: The text to search for. Empty queries return no results.

        Returns:
            A list of SearchResult objects ordered by chapter index and offset.

        Raises:
            RuntimeError: If no EPUB is open.
        """
        if self._zip is None:
            raise RuntimeError("No EPUB is open")

        if not query or not query.strip():
            return []

        results: list[SearchResult] = []
        query_lower = query.lower()
        context_chars = 40  # Characters of context on each side of match

        for chapter_idx in range(len(self._spine)):
            try:
                raw_html = self.get_chapter_raw_html(chapter_idx)
            except (RuntimeError, IndexError):
                continue

            plain_text = _strip_html_tags(raw_html)
            text_lower = plain_text.lower()

            # Find all occurrences
            start = 0
            while True:
                pos = text_lower.find(query_lower, start)
                if pos == -1:
                    break

                # Extract context around the match
                context_start = max(0, pos - context_chars)
                context_end = min(len(plain_text), pos + len(query) + context_chars)
                match_text = plain_text[context_start:context_end]

                # Add ellipsis for truncated context
                if context_start > 0:
                    match_text = "..." + match_text
                if context_end < len(plain_text):
                    match_text = match_text + "..."

                results.append(SearchResult(
                    chapter_index=chapter_idx,
                    match_text=match_text,
                    offset=pos,
                ))

                start = pos + 1  # Move past this match

        return results

    def get_flat_toc(self) -> list[TocEntry]:
        """Get the table of contents as a flat list for linear navigation.

        Returns:
            A flat list of all TocEntry objects in reading order (depth-first).
        """
        return flatten_toc(self._toc)

    # --- Internal parsing methods ---

    def _parse_container(self) -> None:
        """Parse META-INF/container.xml to find the OPF file path."""
        container_xml = self._read_zip_file("META-INF/container.xml")
        root = ET.fromstring(container_xml)

        rootfiles = root.find(
            ".//container:rootfile",
            NAMESPACES,
        )
        if rootfiles is None:
            # Try without namespace (some EPUBs)
            rootfiles = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")

        if rootfiles is None:
            raise RuntimeError("No rootfile found in container.xml")

        self._opf_path = rootfiles.get("full-path", "")
        if not self._opf_path:
            raise RuntimeError("Empty full-path in container.xml rootfile")

        # Determine OPF directory for resolving relative paths
        self._opf_dir = str(PurePosixPath(self._opf_path).parent)
        if self._opf_dir == ".":
            self._opf_dir = ""

    def _parse_opf(self) -> None:
        """Parse the OPF file to extract metadata, manifest, and spine."""
        opf_xml = self._read_zip_file(self._opf_path)
        root = ET.fromstring(opf_xml)

        self._parse_metadata_from_opf(root)
        self._parse_manifest_from_opf(root)
        self._parse_spine_from_opf(root)

    def _parse_metadata_from_opf(self, root: ET.Element) -> None:
        """Extract metadata from OPF XML."""
        metadata_el = root.find("opf:metadata", NAMESPACES)
        if metadata_el is None:
            metadata_el = root.find("{http://www.idpf.org/2007/opf}metadata")
        if metadata_el is None:
            return

        def _get_text(tag: str, ns: str = "dc") -> str:
            el = metadata_el.find(f"{ns}:{tag}", NAMESPACES)
            if el is None:
                el = metadata_el.find(
                    f"{{{NAMESPACES.get(ns, '')}}}{tag}"
                )
            return el.text.strip() if el is not None and el.text else ""

        self._metadata = EPUBMetadata(
            title=_get_text("title"),
            author=_get_text("creator"),
            publisher=_get_text("publisher"),
            language=_get_text("language"),
            identifier=_get_text("identifier"),
            description=_get_text("description"),
        )

    def _parse_manifest_from_opf(self, root: ET.Element) -> None:
        """Extract manifest items from OPF XML."""
        manifest_el = root.find("opf:manifest", NAMESPACES)
        if manifest_el is None:
            manifest_el = root.find("{http://www.idpf.org/2007/opf}manifest")
        if manifest_el is None:
            return

        self._manifest = {}
        for item in manifest_el:
            item_id = item.get("id", "")
            if item_id:
                self._manifest[item_id] = {
                    "href": item.get("href", ""),
                    "media-type": item.get("media-type", ""),
                }

    def _parse_spine_from_opf(self, root: ET.Element) -> None:
        """Extract spine (reading order) from OPF XML."""
        spine_el = root.find("opf:spine", NAMESPACES)
        if spine_el is None:
            spine_el = root.find("{http://www.idpf.org/2007/opf}spine")
        if spine_el is None:
            return

        self._spine = []
        for itemref in spine_el:
            idref = itemref.get("idref", "")
            linear = itemref.get("linear", "yes") != "no"
            if idref and idref in self._manifest:
                manifest_item = self._manifest[idref]
                self._spine.append(
                    SpineItem(
                        id=idref,
                        href=manifest_item["href"],
                        media_type=manifest_item.get("media-type", "application/xhtml+xml"),
                        linear=linear,
                    )
                )

    def _parse_toc(self) -> None:
        """Parse the table of contents (NCX or NAV).

        Tries NAV document first (EPUB 3), falls back to NCX (EPUB 2).
        """
        # Try EPUB 3 NAV
        nav_item = self._find_nav_document()
        if nav_item:
            self._parse_nav_toc(nav_item)
            return

        # Try EPUB 2 NCX
        ncx_item = self._find_ncx_document()
        if ncx_item:
            self._parse_ncx_toc(ncx_item)

    def _find_nav_document(self) -> str | None:
        """Find the EPUB 3 navigation document in the manifest."""
        for item_id, item_data in self._manifest.items():
            href = item_data.get("href", "")
            # NAV documents are typically identified by properties="nav"
            # but since we don't store properties, look for nav.xhtml
            if "nav" in item_id.lower() and "xhtml" in item_data.get("media-type", ""):
                return href
        return None

    def _find_ncx_document(self) -> str | None:
        """Find the EPUB 2 NCX file in the manifest."""
        for item_id, item_data in self._manifest.items():
            if item_data.get("media-type") == "application/x-dtbncx+xml":
                return item_data.get("href", "")
        return None

    def _parse_nav_toc(self, nav_href: str) -> None:
        """Parse EPUB 3 NAV document for table of contents."""
        nav_path = self._resolve_path(nav_href)
        try:
            nav_html = self._read_zip_file(nav_path)
        except (KeyError, RuntimeError):
            return

        root = ET.fromstring(nav_html)
        # Find the nav element with epub:type="toc"
        nav_el = None
        for nav in root.iter("{http://www.w3.org/1999/xhtml}nav"):
            if nav.get("{http://www.idpf.org/2007/ops}type") == "toc":
                nav_el = nav
                break

        if nav_el is None:
            # Fallback: look for any nav element
            for nav in root.iter("{http://www.w3.org/1999/xhtml}nav"):
                nav_el = nav
                break

        if nav_el is None:
            return

        # Parse the ol/li structure
        ol = nav_el.find("{http://www.w3.org/1999/xhtml}ol")
        if ol is not None:
            self._toc = self._parse_nav_ol(ol)

    def _parse_nav_ol(self, ol_element: ET.Element) -> list[TocEntry]:
        """Recursively parse a NAV ol element."""
        entries = []
        for li in ol_element.findall("{http://www.w3.org/1999/xhtml}li"):
            a = li.find("{http://www.w3.org/1999/xhtml}a")
            if a is not None:
                title = "".join(a.itertext()).strip()
                href = a.get("href", "")
                entry = TocEntry(title=title, href=href)

                # Check for nested ol
                nested_ol = li.find("{http://www.w3.org/1999/xhtml}ol")
                if nested_ol is not None:
                    entry.children = self._parse_nav_ol(nested_ol)

                entries.append(entry)
        return entries

    def _parse_ncx_toc(self, ncx_href: str) -> None:
        """Parse EPUB 2 NCX document for table of contents."""
        ncx_path = self._resolve_path(ncx_href)
        try:
            ncx_xml = self._read_zip_file(ncx_path)
        except (KeyError, RuntimeError):
            return

        root = ET.fromstring(ncx_xml)
        nav_map = root.find("{http://www.daisy.org/z3986/2005/ncx/}navMap")
        if nav_map is None:
            # Try without namespace
            nav_map = root.find("navMap")
        if nav_map is None:
            return

        self._toc = self._parse_ncx_nav_points(nav_map)

    def _parse_ncx_nav_points(self, parent: ET.Element) -> list[TocEntry]:
        """Recursively parse NCX navPoint elements."""
        entries = []
        ns = "{http://www.daisy.org/z3986/2005/ncx/}"

        for nav_point in parent.findall(f"{ns}navPoint"):
            label_el = nav_point.find(f"{ns}navLabel/{ns}text")
            content_el = nav_point.find(f"{ns}content")

            title = label_el.text.strip() if label_el is not None and label_el.text else ""
            href = content_el.get("src", "") if content_el is not None else ""

            entry = TocEntry(title=title, href=href)
            # Recursively parse nested navPoints
            entry.children = self._parse_ncx_nav_points(nav_point)
            entries.append(entry)

        return entries

    # --- Internal helper methods ---

    def _resolve_path(self, href: str) -> str:
        """Resolve a relative href to an absolute path within the EPUB zip.

        Args:
            href: Relative path from the OPF directory.

        Returns:
            Absolute path within the zip file.
        """
        if not self._opf_dir:
            return href
        return posixpath.normpath(posixpath.join(self._opf_dir, href))

    def _read_zip_file(self, path: str) -> str:
        """Read a text file from the EPUB zip archive.

        Args:
            path: Path within the zip archive.

        Returns:
            The file contents as a string.

        Raises:
            RuntimeError: If the file cannot be read.
        """
        if self._zip is None:
            raise RuntimeError("No EPUB is open")
        try:
            return self._zip.read(path).decode("utf-8")
        except KeyError:
            raise RuntimeError(f"File not found in EPUB: {path}")
        except UnicodeDecodeError:
            # Try latin-1 as fallback
            return self._zip.read(path).decode("latin-1")

    def _build_injected_css(self) -> str:
        """Build the combined CSS to inject into chapter HTML.

        Combines font settings, theme, highlights, and view mode CSS.

        Returns:
            Combined CSS string.
        """
        parts = []

        # Font settings CSS
        parts.append(generate_font_css(self._font_settings))

        # Dark mode CSS
        if self._dark_mode:
            parts.append(generate_dark_mode_css())

        # Annotation highlights CSS
        if self._highlights:
            parts.append(generate_highlight_css(self._highlights))

        # View mode CSS
        if self._view_mode == EPUBViewMode.PAGINATED:
            parts.append(
                generate_pagination_css(self._viewport_width, self._viewport_height)
            )
        else:
            parts.append(generate_scroll_css())

        return "\n".join(parts)

    def _inject_css_into_html(self, html: str, css: str) -> str:
        """Inject a CSS style block into HTML content.

        Injects a <style> element just before </head> if a <head> element
        exists, otherwise prepends it to the HTML.

        Args:
            html: The original HTML content.
            css: The CSS to inject.

        Returns:
            HTML with injected CSS.
        """
        style_block = f"<style type=\"text/css\">\n{css}\n</style>\n"

        # Try to inject before </head>
        head_close_lower = html.lower().find("</head>")
        if head_close_lower != -1:
            return html[:head_close_lower] + style_block + html[head_close_lower:]

        # Fallback: inject after <head> if exists
        head_open_lower = html.lower().find("<head")
        if head_open_lower != -1:
            # Find the end of the <head> tag
            head_tag_end = html.find(">", head_open_lower)
            if head_tag_end != -1:
                insert_pos = head_tag_end + 1
                return html[:insert_pos] + "\n" + style_block + html[insert_pos:]

        # Last fallback: prepend to content
        return style_block + html
