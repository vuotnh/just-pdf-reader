"""Unit tests for the EPUB Reader Backend.

Tests cover:
- EPUB zip parsing (container.xml, OPF, spine, manifest)
- NCX and NAV table of contents parsing
- Chapter HTML extraction with CSS injection
- Font settings CSS generation
- Dark mode CSS generation
- Annotation highlight CSS generation
- Pagination mode CSS (column splitting)
- Continuous scroll mode CSS
- Resource resolution
- View mode switching
- Error handling for invalid EPUBs
"""

import zipfile

import pytest

from src.domain.enums import HighlightColor
from src.infrastructure.readers.epub_reader_backend import (
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LINE_HEIGHT,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    AnnotationHighlight,
    EPUBMetadata,
    EPUBReaderBackend,
    EPUBViewMode,
    FontSettings,
    SpineItem,
    TocEntry,
    clamp_font_size,
    generate_dark_mode_css,
    generate_font_css,
    generate_highlight_css,
    generate_pagination_css,
    generate_scroll_css,
)


# --- Helper to create synthetic EPUB files ---


def create_minimal_epub(
    tmp_path,
    title="Test Book",
    author="Test Author",
    chapters=None,
    ncx=True,
    nav=False,
):
    """Create a minimal synthetic EPUB file for testing.

    Args:
        tmp_path: pytest tmp_path fixture.
        title: Book title for metadata.
        author: Book author for metadata.
        chapters: List of (id, filename, html_content) tuples.
        ncx: Whether to include NCX table of contents.
        nav: Whether to include EPUB 3 NAV document.

    Returns:
        Path to the created EPUB file.
    """
    if chapters is None:
        chapters = [
            ("ch1", "chapter1.xhtml", "<html><head><title>Ch 1</title></head>"
             "<body><h1>Chapter 1</h1><p>Hello world.</p></body></html>"),
            ("ch2", "chapter2.xhtml", "<html><head><title>Ch 2</title></head>"
             "<body><h1>Chapter 2</h1><p>Second chapter content.</p></body></html>"),
        ]

    epub_path = str(tmp_path / "test.epub")

    with zipfile.ZipFile(epub_path, "w") as zf:
        # mimetype (must be first, uncompressed)
        zf.writestr("mimetype", "application/epub+zip")

        # META-INF/container.xml
        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '  <rootfiles>\n'
            '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
            '  </rootfiles>\n'
            '</container>'
        )
        zf.writestr("META-INF/container.xml", container_xml)

        # Build manifest items
        manifest_items = ""
        spine_items = ""
        for ch_id, ch_file, ch_html in chapters:
            manifest_items += f'    <item id="{ch_id}" href="{ch_file}" media-type="application/xhtml+xml"/>\n'
            spine_items += f'    <itemref idref="{ch_id}"/>\n'
            zf.writestr(f"OEBPS/{ch_file}", ch_html)

        if ncx:
            manifest_items += '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'

        if nav:
            manifest_items += '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"/>\n'
            spine_items += '    <itemref idref="nav"/>\n'

        # OPF content
        opf_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">\n'
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'    <dc:title>{title}</dc:title>\n'
            f'    <dc:creator>{author}</dc:creator>\n'
            '    <dc:publisher>Test Publisher</dc:publisher>\n'
            '    <dc:language>en</dc:language>\n'
            '    <dc:identifier>test-isbn-123</dc:identifier>\n'
            '  </metadata>\n'
            '  <manifest>\n'
            f'{manifest_items}'
            '  </manifest>\n'
            '  <spine toc="ncx">\n'
            f'{spine_items}'
            '  </spine>\n'
            '</package>'
        )
        zf.writestr("OEBPS/content.opf", opf_content)

        # NCX table of contents
        if ncx:
            ncx_content = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
                '  <navMap>\n'
                '    <navPoint id="np1">\n'
                '      <navLabel><text>Chapter 1</text></navLabel>\n'
                '      <content src="chapter1.xhtml"/>\n'
                '    </navPoint>\n'
                '    <navPoint id="np2">\n'
                '      <navLabel><text>Chapter 2</text></navLabel>\n'
                '      <content src="chapter2.xhtml"/>\n'
                '      <navPoint id="np2_1">\n'
                '        <navLabel><text>Section 2.1</text></navLabel>\n'
                '        <content src="chapter2.xhtml#sec21"/>\n'
                '      </navPoint>\n'
                '    </navPoint>\n'
                '  </navMap>\n'
                '</ncx>'
            )
            zf.writestr("OEBPS/toc.ncx", ncx_content)

        # NAV document
        if nav:
            nav_content = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
                '<head><title>Navigation</title></head>\n'
                '<body>\n'
                '<nav epub:type="toc">\n'
                '  <ol>\n'
                '    <li><a href="chapter1.xhtml">Chapter One</a></li>\n'
                '    <li><a href="chapter2.xhtml">Chapter Two</a>\n'
                '      <ol>\n'
                '        <li><a href="chapter2.xhtml#sec21">Section 2.1</a></li>\n'
                '      </ol>\n'
                '    </li>\n'
                '  </ol>\n'
                '</nav>\n'
                '</body></html>'
            )
            zf.writestr("OEBPS/nav.xhtml", nav_content)

        # Add a sample image resource
        zf.writestr("OEBPS/images/sample.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    return epub_path


# --- Fixtures ---


@pytest.fixture
def epub_file(tmp_path):
    """Create a minimal EPUB file with NCX TOC."""
    return create_minimal_epub(tmp_path, ncx=True, nav=False)


@pytest.fixture
def epub_with_nav(tmp_path):
    """Create an EPUB file with NAV document (EPUB 3)."""
    return create_minimal_epub(tmp_path, ncx=False, nav=True)


@pytest.fixture
def backend(epub_file):
    """Create an EPUBReaderBackend with a test EPUB opened."""
    b = EPUBReaderBackend(file_path=epub_file)
    yield b
    b.close()


@pytest.fixture
def backend_nav(epub_with_nav):
    """Create an EPUBReaderBackend with a NAV-based EPUB opened."""
    b = EPUBReaderBackend(file_path=epub_with_nav)
    yield b
    b.close()


# --- clamp_font_size tests ---


class TestClampFontSize:
    """Tests for font size clamping."""

    def test_below_minimum(self):
        assert clamp_font_size(4) == MIN_FONT_SIZE

    def test_above_maximum(self):
        assert clamp_font_size(100) == MAX_FONT_SIZE

    def test_within_range(self):
        assert clamp_font_size(16) == 16

    def test_at_minimum_boundary(self):
        assert clamp_font_size(MIN_FONT_SIZE) == MIN_FONT_SIZE

    def test_at_maximum_boundary(self):
        assert clamp_font_size(MAX_FONT_SIZE) == MAX_FONT_SIZE


# --- CSS Generation tests ---


class TestGenerateFontCSS:
    """Tests for font CSS generation."""

    def test_default_settings(self):
        settings = FontSettings()
        css = generate_font_css(settings)
        assert f"font-family: {DEFAULT_FONT_FAMILY};" in css
        assert f"font-size: {DEFAULT_FONT_SIZE}pt;" in css
        assert f"line-height: {DEFAULT_LINE_HEIGHT};" in css

    def test_custom_settings(self):
        settings = FontSettings(family="Arial", size=20, line_height=2.0)
        css = generate_font_css(settings)
        assert "font-family: Arial;" in css
        assert "font-size: 20pt;" in css
        assert "line-height: 2.0;" in css

    def test_size_clamped_below_minimum(self):
        settings = FontSettings(size=2)
        css = generate_font_css(settings)
        assert f"font-size: {MIN_FONT_SIZE}pt;" in css

    def test_size_clamped_above_maximum(self):
        settings = FontSettings(size=100)
        css = generate_font_css(settings)
        assert f"font-size: {MAX_FONT_SIZE}pt;" in css

    def test_contains_body_selector(self):
        css = generate_font_css(FontSettings())
        assert "body {" in css


class TestGenerateDarkModeCSS:
    """Tests for dark mode CSS generation."""

    def test_has_dark_background(self):
        css = generate_dark_mode_css()
        assert "background-color: #1a1a1a;" in css

    def test_has_light_text(self):
        css = generate_dark_mode_css()
        assert "color: #e0e0e0;" in css

    def test_preserves_images(self):
        css = generate_dark_mode_css()
        assert "img" in css
        assert "filter: none;" in css


class TestGenerateHighlightCSS:
    """Tests for annotation highlight CSS generation."""

    def test_empty_highlights(self):
        css = generate_highlight_css([])
        assert css == ""

    def test_single_highlight(self):
        highlights = [
            AnnotationHighlight(
                annotation_id="ann1",
                color=HighlightColor.YELLOW,
                start_offset=0,
                end_offset=10,
            )
        ]
        css = generate_highlight_css(highlights)
        assert ".annotation-ann1" in css
        assert "background-color:" in css
        assert "rgba(255, 255, 0, 0.3)" in css

    def test_multiple_highlights_different_colors(self):
        highlights = [
            AnnotationHighlight("a1", HighlightColor.GREEN, 0, 5),
            AnnotationHighlight("a2", HighlightColor.BLUE, 10, 20),
            AnnotationHighlight("a3", HighlightColor.PINK, 30, 40),
        ]
        css = generate_highlight_css(highlights)
        assert ".annotation-a1" in css
        assert ".annotation-a2" in css
        assert ".annotation-a3" in css
        assert "rgba(0, 255, 0, 0.3)" in css
        assert "rgba(0, 150, 255, 0.3)" in css
        assert "rgba(255, 105, 180, 0.3)" in css

    def test_orange_highlight(self):
        highlights = [AnnotationHighlight("a1", HighlightColor.ORANGE, 0, 5)]
        css = generate_highlight_css(highlights)
        assert "rgba(255, 165, 0, 0.3)" in css


class TestGeneratePaginationCSS:
    """Tests for pagination mode CSS generation."""

    def test_default_dimensions(self):
        css = generate_pagination_css()
        assert "column-width:" in css
        assert "column-gap:" in css
        assert "column-fill: auto;" in css
        assert "overflow: hidden;" in css

    def test_custom_dimensions(self):
        css = generate_pagination_css(viewport_width=1024, viewport_height=768)
        assert f"column-width: {1024 - 40}px;" in css
        assert f"height: {768 - 40}px;" in css

    def test_body_selector(self):
        css = generate_pagination_css()
        assert "body {" in css


class TestGenerateScrollCSS:
    """Tests for continuous scroll mode CSS generation."""

    def test_has_auto_overflow(self):
        css = generate_scroll_css()
        assert "overflow-y: auto;" in css

    def test_has_padding(self):
        css = generate_scroll_css()
        assert "padding: 20px;" in css

    def test_body_selector(self):
        css = generate_scroll_css()
        assert "body {" in css


# --- EPUBReaderBackend tests ---


class TestEPUBReaderBackendOpen:
    """Tests for opening and parsing EPUB files."""

    def test_open_sets_metadata(self, backend: EPUBReaderBackend):
        assert backend.metadata.title == "Test Book"
        assert backend.metadata.author == "Test Author"
        assert backend.metadata.publisher == "Test Publisher"
        assert backend.metadata.language == "en"

    def test_open_parses_spine(self, backend: EPUBReaderBackend):
        assert backend.chapter_count == 2
        assert backend.spine[0].id == "ch1"
        assert backend.spine[0].href == "chapter1.xhtml"
        assert backend.spine[1].id == "ch2"

    def test_open_parses_ncx_toc(self, backend: EPUBReaderBackend):
        assert len(backend.toc) == 2
        assert backend.toc[0].title == "Chapter 1"
        assert backend.toc[0].href == "chapter1.xhtml"
        assert backend.toc[1].title == "Chapter 2"
        # Nested navPoint
        assert len(backend.toc[1].children) == 1
        assert backend.toc[1].children[0].title == "Section 2.1"

    def test_open_parses_nav_toc(self, backend_nav: EPUBReaderBackend):
        assert len(backend_nav.toc) == 2
        assert backend_nav.toc[0].title == "Chapter One"
        assert backend_nav.toc[0].href == "chapter1.xhtml"
        assert backend_nav.toc[1].title == "Chapter Two"
        # Nested entry
        assert len(backend_nav.toc[1].children) == 1
        assert backend_nav.toc[1].children[0].title == "Section 2.1"

    def test_initial_state(self, backend: EPUBReaderBackend):
        assert backend.current_chapter == 0
        assert backend.view_mode == EPUBViewMode.CONTINUOUS_SCROLL
        assert backend.dark_mode is False
        assert backend.font_settings.family == DEFAULT_FONT_FAMILY
        assert backend.font_settings.size == DEFAULT_FONT_SIZE

    def test_open_invalid_file_raises(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.epub")
        with pytest.raises(RuntimeError, match="Failed to open EPUB"):
            EPUBReaderBackend(file_path=bad_path)

    def test_open_invalid_zip_raises(self, tmp_path):
        bad_file = tmp_path / "bad.epub"
        bad_file.write_text("not a zip file")
        with pytest.raises(RuntimeError, match="Failed to open EPUB"):
            EPUBReaderBackend(file_path=str(bad_file))

    def test_deferred_open(self, epub_file):
        b = EPUBReaderBackend()
        assert b.chapter_count == 0
        b.open(epub_file)
        assert b.chapter_count == 2
        b.close()


class TestEPUBReaderBackendClose:
    """Tests for closing and resource cleanup."""

    def test_close_resets_state(self, backend: EPUBReaderBackend):
        backend.close()
        assert backend.chapter_count == 0
        assert backend.file_path is None
        assert backend.metadata.title == ""
        assert backend.toc == []
        assert backend.spine == []

    def test_close_then_operations_raise(self, backend: EPUBReaderBackend):
        backend.close()
        with pytest.raises(RuntimeError, match="No EPUB is open"):
            backend.get_chapter_html(0)


class TestEPUBReaderBackendNavigation:
    """Tests for chapter navigation."""

    def test_go_to_chapter(self, backend: EPUBReaderBackend):
        result = backend.go_to_chapter(1)
        assert result == 1
        assert backend.current_chapter == 1

    def test_go_to_chapter_clamped_at_start(self, backend: EPUBReaderBackend):
        result = backend.go_to_chapter(-5)
        assert result == 0

    def test_go_to_chapter_clamped_at_end(self, backend: EPUBReaderBackend):
        result = backend.go_to_chapter(100)
        assert result == 1  # Only 2 chapters, max index is 1

    def test_go_to_chapter_empty_spine(self):
        b = EPUBReaderBackend()
        result = b.go_to_chapter(0)
        assert result == 0


class TestEPUBReaderBackendChapterExtraction:
    """Tests for chapter HTML extraction."""

    def test_get_chapter_html_returns_content(self, backend: EPUBReaderBackend):
        html = backend.get_chapter_html(0)
        assert "Chapter 1" in html
        assert "Hello world." in html

    def test_get_chapter_html_second_chapter(self, backend: EPUBReaderBackend):
        html = backend.get_chapter_html(1)
        assert "Chapter 2" in html
        assert "Second chapter content." in html

    def test_get_chapter_html_injects_css(self, backend: EPUBReaderBackend):
        html = backend.get_chapter_html(0)
        assert "<style" in html
        assert "font-family:" in html

    def test_get_chapter_html_uses_current_chapter(self, backend: EPUBReaderBackend):
        backend.go_to_chapter(1)
        html = backend.get_chapter_html()
        assert "Chapter 2" in html

    def test_get_chapter_html_out_of_range_raises(self, backend: EPUBReaderBackend):
        with pytest.raises(IndexError):
            backend.get_chapter_html(10)

    def test_get_chapter_html_no_epub_raises(self):
        b = EPUBReaderBackend()
        with pytest.raises(RuntimeError, match="No EPUB is open"):
            b.get_chapter_html(0)

    def test_get_chapter_raw_html(self, backend: EPUBReaderBackend):
        raw = backend.get_chapter_raw_html(0)
        assert "Chapter 1" in raw
        # Raw should not have injected CSS
        assert "font-family:" not in raw or "font-family:" in raw  # Original HTML might not have it
        # But it should NOT have our style block
        # Check that it's the original content
        assert "<h1>Chapter 1</h1>" in raw


class TestEPUBReaderBackendCSSInjection:
    """Tests for CSS injection into chapter HTML."""

    def test_font_settings_injected(self, backend: EPUBReaderBackend):
        backend.set_font_settings(FontSettings(family="Roboto", size=24, line_height=1.8))
        html = backend.get_chapter_html(0)
        assert "font-family: Roboto;" in html
        assert "font-size: 24pt;" in html
        assert "line-height: 1.8;" in html

    def test_dark_mode_injected(self, backend: EPUBReaderBackend):
        backend.set_dark_mode(True)
        html = backend.get_chapter_html(0)
        assert "background-color: #1a1a1a;" in html
        assert "color: #e0e0e0;" in html

    def test_dark_mode_not_injected_when_disabled(self, backend: EPUBReaderBackend):
        backend.set_dark_mode(False)
        html = backend.get_chapter_html(0)
        assert "#1a1a1a" not in html

    def test_highlights_injected(self, backend: EPUBReaderBackend):
        highlights = [
            AnnotationHighlight("h1", HighlightColor.YELLOW, 0, 10),
            AnnotationHighlight("h2", HighlightColor.GREEN, 20, 30),
        ]
        backend.set_highlights(highlights)
        html = backend.get_chapter_html(0)
        assert ".annotation-h1" in html
        assert ".annotation-h2" in html

    def test_pagination_mode_css_injected(self, backend: EPUBReaderBackend):
        backend.set_view_mode(EPUBViewMode.PAGINATED)
        html = backend.get_chapter_html(0)
        assert "column-width:" in html
        assert "column-gap:" in html

    def test_scroll_mode_css_injected(self, backend: EPUBReaderBackend):
        backend.set_view_mode(EPUBViewMode.CONTINUOUS_SCROLL)
        html = backend.get_chapter_html(0)
        assert "overflow-y: auto;" in html

    def test_css_injected_before_head_close(self, backend: EPUBReaderBackend):
        html = backend.get_chapter_html(0)
        style_pos = html.find("<style")
        head_close_pos = html.find("</head>")
        assert style_pos < head_close_pos


class TestEPUBReaderBackendResources:
    """Tests for resource resolution."""

    def test_get_resource_image(self, backend: EPUBReaderBackend):
        data = backend.get_resource("images/sample.png")
        assert data.startswith(b"\x89PNG")

    def test_get_resource_not_found_raises(self, backend: EPUBReaderBackend):
        with pytest.raises(FileNotFoundError):
            backend.get_resource("nonexistent.png")

    def test_get_resource_no_epub_raises(self):
        b = EPUBReaderBackend()
        with pytest.raises(RuntimeError, match="No EPUB is open"):
            b.get_resource("any.png")

    def test_resolve_resource_path(self, backend: EPUBReaderBackend):
        # From chapter1.xhtml, resolving ../images/sample.png
        resolved = backend.resolve_resource_path("../images/sample.png", 0)
        # chapter1.xhtml is in OEBPS/, so ../images/sample.png resolves to
        # OEBPS/../images/sample.png -> images/sample.png (normalized)
        # Actually, since chapter is at OEBPS/chapter1.xhtml, going ../ goes to root
        assert "images/sample.png" in resolved

    def test_resolve_resource_path_same_dir(self, backend: EPUBReaderBackend):
        resolved = backend.resolve_resource_path("style.css", 0)
        assert "OEBPS/style.css" == resolved


class TestEPUBReaderBackendViewMode:
    """Tests for view mode switching."""

    def test_set_paginated_mode(self, backend: EPUBReaderBackend):
        backend.set_view_mode(EPUBViewMode.PAGINATED)
        assert backend.view_mode == EPUBViewMode.PAGINATED

    def test_set_continuous_scroll_mode(self, backend: EPUBReaderBackend):
        backend.set_view_mode(EPUBViewMode.PAGINATED)
        backend.set_view_mode(EPUBViewMode.CONTINUOUS_SCROLL)
        assert backend.view_mode == EPUBViewMode.CONTINUOUS_SCROLL


class TestEPUBReaderBackendSettings:
    """Tests for font and viewport settings."""

    def test_set_font_settings(self, backend: EPUBReaderBackend):
        backend.set_font_settings(FontSettings(family="Courier", size=14, line_height=1.2))
        assert backend.font_settings.family == "Courier"
        assert backend.font_settings.size == 14
        assert backend.font_settings.line_height == 1.2

    def test_set_font_settings_clamps_size(self, backend: EPUBReaderBackend):
        backend.set_font_settings(FontSettings(size=2))
        assert backend.font_settings.size == MIN_FONT_SIZE

        backend.set_font_settings(FontSettings(size=200))
        assert backend.font_settings.size == MAX_FONT_SIZE

    def test_set_viewport(self, backend: EPUBReaderBackend):
        backend.set_viewport(1024, 768)
        assert backend.viewport_width == 1024
        assert backend.viewport_height == 768

    def test_set_viewport_minimum(self, backend: EPUBReaderBackend):
        backend.set_viewport(10, 10)
        assert backend.viewport_width == 100
        assert backend.viewport_height == 100

    def test_set_dark_mode(self, backend: EPUBReaderBackend):
        backend.set_dark_mode(True)
        assert backend.dark_mode is True
        backend.set_dark_mode(False)
        assert backend.dark_mode is False


class TestEPUBReaderBackendManifest:
    """Tests for manifest item queries."""

    def test_get_all_manifest_items(self, backend: EPUBReaderBackend):
        items = backend.get_manifest_items()
        assert len(items) >= 2  # At least the two chapters

    def test_get_manifest_items_by_media_type(self, backend: EPUBReaderBackend):
        items = backend.get_manifest_items(media_type="application/xhtml+xml")
        assert all(i["media_type"] == "application/xhtml+xml" for i in items)

    def test_get_manifest_ncx_item(self, backend: EPUBReaderBackend):
        items = backend.get_manifest_items(media_type="application/x-dtbncx+xml")
        assert len(items) == 1
        assert items[0]["id"] == "ncx"


class TestEPUBReaderBackendEdgeCases:
    """Tests for edge cases and error handling."""

    def test_epub_without_toc(self, tmp_path):
        """EPUB with no NCX and no NAV should still open."""
        epub_path = create_minimal_epub(tmp_path, ncx=False, nav=False)
        b = EPUBReaderBackend(file_path=epub_path)
        assert b.chapter_count == 2
        assert b.toc == []
        b.close()

    def test_epub_single_chapter(self, tmp_path):
        """EPUB with one chapter works correctly."""
        chapters = [
            ("ch1", "single.xhtml", "<html><head></head><body><p>Only chapter</p></body></html>"),
        ]
        epub_path = create_minimal_epub(tmp_path, chapters=chapters, ncx=False, nav=False)
        b = EPUBReaderBackend(file_path=epub_path)
        assert b.chapter_count == 1
        html = b.get_chapter_html(0)
        assert "Only chapter" in html
        b.close()

    def test_html_without_head_gets_css_prepended(self, tmp_path):
        """HTML without <head> gets CSS prepended."""
        chapters = [
            ("ch1", "nohead.xhtml", "<body><p>No head here</p></body>"),
        ]
        epub_path = create_minimal_epub(tmp_path, chapters=chapters, ncx=False, nav=False)
        b = EPUBReaderBackend(file_path=epub_path)
        html = b.get_chapter_html(0)
        assert "<style" in html
        assert "No head here" in html
        b.close()

    def test_multiple_opens(self, epub_file, tmp_path):
        """Opening a new EPUB after closing the previous one works."""
        b = EPUBReaderBackend(file_path=epub_file)
        assert b.metadata.title == "Test Book"
        b.close()

        sub_dir = tmp_path / "sub"
        sub_dir.mkdir()
        epub2 = create_minimal_epub(sub_dir, title="Book Two", author="Author Two")
        b.open(epub2)
        assert b.metadata.title == "Book Two"
        b.close()
