"""Unit tests for the EPUB Reader QML Controller.

Tests cover:
- Opening and closing EPUB documents
- Chapter navigation (goToChapter, nextChapter, previousChapter)
- Font settings (setFont with clamping)
- Theme switching (setTheme dark/light)
- View mode switching (setPageMode)
- Text search with result navigation
- Bookmark management (addBookmark)
- TOC model population
- Error handling
- Reading position save/restore
"""

import zipfile

import pytest

from src.infrastructure.readers.epub_reader_backend import (
    EPUBReaderBackend,
    EPUBViewMode,
    FontSettings,
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
)
from src.infrastructure.readers.webengine_bridge import (
    ReadingPositionState,
    WebEngineBridge,
)
from src.presentation.controllers.epub_reader_controller import (
    EPUBReaderController,
    EPUBSearchResultModel,
    EPUBTocListModel,
    _resolve_toc_href_to_chapter,
)


# --- Helper to create synthetic EPUB files ---


def create_test_epub(tmp_path, title="Test Book", chapters=None):
    """Create a minimal synthetic EPUB file for testing.

    Args:
        tmp_path: pytest tmp_path fixture.
        title: Book title for metadata.
        chapters: List of (id, filename, html_content) tuples.

    Returns:
        Path to the created EPUB file as a string.
    """
    if chapters is None:
        chapters = [
            ("ch1", "chapter1.xhtml",
             "<html><head><title>Ch 1</title></head>"
             "<body><h1>Chapter 1</h1><p>Hello world. This is the first chapter.</p></body></html>"),
            ("ch2", "chapter2.xhtml",
             "<html><head><title>Ch 2</title></head>"
             "<body><h1>Chapter 2</h1><p>Second chapter content with searchable text.</p></body></html>"),
            ("ch3", "chapter3.xhtml",
             "<html><head><title>Ch 3</title></head>"
             "<body><h1>Chapter 3</h1><p>Third chapter. Also has searchable text here.</p></body></html>"),
        ]

    epub_path = str(tmp_path / "test.epub")

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")

        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '  <rootfiles>\n'
            '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
            '  </rootfiles>\n'
            '</container>'
        )
        zf.writestr("META-INF/container.xml", container_xml)

        manifest_items = ""
        spine_items = ""
        for ch_id, ch_file, ch_html in chapters:
            manifest_items += f'    <item id="{ch_id}" href="{ch_file}" media-type="application/xhtml+xml"/>\n'
            spine_items += f'    <itemref idref="{ch_id}"/>\n'
            zf.writestr(f"OEBPS/{ch_file}", ch_html)

        manifest_items += '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'

        opf_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">\n'
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            f'    <dc:title>{title}</dc:title>\n'
            '    <dc:creator>Test Author</dc:creator>\n'
            '    <dc:language>en</dc:language>\n'
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
            '    </navPoint>\n'
            '    <navPoint id="np3">\n'
            '      <navLabel><text>Chapter 3</text></navLabel>\n'
            '      <content src="chapter3.xhtml"/>\n'
            '    </navPoint>\n'
            '  </navMap>\n'
            '</ncx>'
        )
        zf.writestr("OEBPS/toc.ncx", ncx_content)

    return epub_path


# --- Fixtures ---


@pytest.fixture
def epub_file(tmp_path):
    """Create a minimal EPUB file with 3 chapters."""
    return create_test_epub(tmp_path)


@pytest.fixture
def controller(epub_file):
    """Create an EPUBReaderController with a test EPUB opened."""
    ctrl = EPUBReaderController()
    ctrl.openEpub(epub_file)
    yield ctrl
    ctrl.closeEpub()


@pytest.fixture
def empty_controller():
    """Create an EPUBReaderController without an EPUB opened."""
    return EPUBReaderController()


# --- Controller opening/closing tests ---


class TestEPUBReaderControllerOpen:
    """Tests for opening EPUB documents."""

    def test_open_epub_sets_chapter_count(self, controller):
        assert controller.chapterCount == 3

    def test_open_epub_sets_current_chapter(self, controller):
        assert controller.currentChapter == 0

    def test_open_epub_populates_toc(self, controller):
        toc_entries = controller.tocModel.get_entries()
        assert len(toc_entries) == 3
        assert toc_entries[0]["title"] == "Chapter 1"
        assert toc_entries[1]["title"] == "Chapter 2"
        assert toc_entries[2]["title"] == "Chapter 3"

    def test_open_epub_emits_signals(self, epub_file):
        ctrl = EPUBReaderController()
        signals_received = []
        ctrl.documentOpened.connect(lambda: signals_received.append("opened"))
        ctrl.chapterCountChanged.connect(lambda c: signals_received.append(f"count:{c}"))
        ctrl.chapterChanged.connect(lambda c: signals_received.append(f"chapter:{c}"))

        ctrl.openEpub(epub_file)

        assert "opened" in signals_received
        assert "count:3" in signals_received
        assert "chapter:0" in signals_received
        ctrl.closeEpub()

    def test_open_invalid_file_emits_error(self, tmp_path):
        ctrl = EPUBReaderController()
        errors = []
        ctrl.errorOccurred.connect(lambda msg: errors.append(msg))
        ctrl.openEpub(str(tmp_path / "nonexistent.epub"))
        assert len(errors) == 1
        assert "Failed to open EPUB" in errors[0]

    def test_close_resets_state(self, controller):
        controller.closeEpub()
        assert controller.chapterCount == 0

    def test_close_emits_signal(self, controller):
        signals_received = []
        controller.documentClosed.connect(lambda: signals_received.append("closed"))
        controller.closeEpub()
        assert "closed" in signals_received


# --- Navigation tests ---


class TestEPUBReaderControllerNavigation:
    """Tests for chapter navigation."""

    def test_go_to_chapter(self, controller):
        controller.goToChapter(2)
        assert controller.currentChapter == 2

    def test_go_to_chapter_emits_signal(self, controller):
        chapters = []
        controller.chapterChanged.connect(lambda c: chapters.append(c))
        controller.goToChapter(1)
        assert 1 in chapters

    def test_next_chapter(self, controller):
        controller.nextChapter()
        assert controller.currentChapter == 1

    def test_next_chapter_at_end_stays(self, controller):
        controller.goToChapter(2)
        controller.nextChapter()
        assert controller.currentChapter == 2

    def test_previous_chapter(self, controller):
        controller.goToChapter(2)
        controller.previousChapter()
        assert controller.currentChapter == 1

    def test_previous_chapter_at_start_stays(self, controller):
        controller.previousChapter()
        assert controller.currentChapter == 0

    def test_go_to_chapter_clamped(self, controller):
        controller.goToChapter(100)
        assert controller.currentChapter == 2  # Last valid chapter

    def test_go_to_chapter_negative_clamped(self, controller):
        controller.goToChapter(-5)
        assert controller.currentChapter == 0


# --- Font settings tests ---


class TestEPUBReaderControllerFont:
    """Tests for font settings."""

    def test_set_font(self, controller):
        controller.setFont("Arial", 20, 1.8)
        assert controller.fontFamily == "Arial"
        assert controller.fontSize == 20
        assert controller.lineHeight == 1.8

    def test_set_font_clamps_size_below_min(self, controller):
        controller.setFont("serif", 2, 1.5)
        assert controller.fontSize == MIN_FONT_SIZE

    def test_set_font_clamps_size_above_max(self, controller):
        controller.setFont("serif", 100, 1.5)
        assert controller.fontSize == MAX_FONT_SIZE

    def test_set_font_clamps_line_height(self, controller):
        controller.setFont("serif", 16, 0.5)
        assert controller.lineHeight == 1.0  # minimum

        controller.setFont("serif", 16, 5.0)
        assert controller.lineHeight == 3.0  # maximum

    def test_set_font_emits_signal(self, controller):
        signals = []
        controller.fontSettingsChanged.connect(lambda: signals.append("font"))
        controller.setFont("Georgia", 14, 1.6)
        assert "font" in signals

    def test_font_settings_applied_to_bridge(self, controller):
        controller.setFont("monospace", 18, 2.0)
        # Verify the bridge received the settings
        bridge = controller.bridge
        assert bridge._font_settings.family == "monospace"
        assert bridge._font_settings.size == 18
        assert bridge._font_settings.line_height == 2.0


# --- Theme tests ---


class TestEPUBReaderControllerTheme:
    """Tests for theme switching."""

    def test_set_dark_mode(self, controller):
        controller.setTheme(True)
        assert controller.darkMode is True

    def test_set_light_mode(self, controller):
        controller.setTheme(True)
        controller.setTheme(False)
        assert controller.darkMode is False

    def test_set_theme_emits_signal(self, controller):
        signals = []
        controller.darkModeChanged.connect(lambda v: signals.append(v))
        controller.setTheme(True)
        assert True in signals

    def test_dark_mode_applied_to_backend(self, controller):
        controller.setTheme(True)
        assert controller.backend.dark_mode is True

    def test_dark_mode_applied_to_bridge(self, controller):
        controller.setTheme(True)
        assert controller.bridge._dark_mode is True


# --- View mode tests ---


class TestEPUBReaderControllerViewMode:
    """Tests for view mode switching."""

    def test_set_paginated_mode(self, controller):
        controller.setPageMode("paginated")
        assert controller.viewMode == "paginated"

    def test_set_continuous_scroll_mode(self, controller):
        controller.setPageMode("paginated")
        controller.setPageMode("continuous_scroll")
        assert controller.viewMode == "continuous_scroll"

    def test_set_invalid_mode_emits_error(self, controller):
        errors = []
        controller.errorOccurred.connect(lambda msg: errors.append(msg))
        controller.setPageMode("invalid_mode")
        assert len(errors) == 1
        assert "Invalid view mode" in errors[0]

    def test_set_mode_emits_signal(self, controller):
        modes = []
        controller.viewModeChanged.connect(lambda m: modes.append(m))
        controller.setPageMode("paginated")
        assert "paginated" in modes


# --- Search tests ---


class TestEPUBReaderControllerSearch:
    """Tests for text search."""

    def test_search_finds_results(self, controller):
        controller.search("searchable")
        assert controller.searchMatchCount == 2  # In chapters 2 and 3

    def test_search_no_results(self, controller):
        controller.search("xyznonexistent")
        assert controller.searchMatchCount == 0

    def test_search_empty_query(self, controller):
        controller.search("")
        assert controller.searchMatchCount == 0
        assert controller.currentMatchIndex == -1

    def test_search_navigates_to_first_match(self, controller):
        controller.search("Second chapter")
        assert controller.searchMatchCount > 0
        assert controller.currentChapter == 1  # Navigated to chapter 2

    def test_search_emits_signals(self, controller):
        result_counts = []
        match_indices = []
        controller.searchResultsChanged.connect(lambda c: result_counts.append(c))
        controller.currentMatchChanged.connect(lambda i: match_indices.append(i))
        controller.search("chapter")
        assert len(result_counts) > 0
        assert len(match_indices) > 0

    def test_next_match(self, controller):
        controller.search("searchable")
        assert controller.currentMatchIndex == 0
        controller.nextMatch()
        assert controller.currentMatchIndex == 1

    def test_prev_match(self, controller):
        controller.search("searchable")
        controller.nextMatch()  # Go to index 1
        controller.prevMatch()  # Back to index 0
        assert controller.currentMatchIndex == 0

    def test_next_match_wraps_around(self, controller):
        controller.search("searchable")
        # Go past last result
        controller.nextMatch()  # index 1
        controller.nextMatch()  # wraps to 0
        assert controller.currentMatchIndex == 0


# --- Bookmark tests ---


class TestEPUBReaderControllerBookmarks:
    """Tests for bookmark management."""

    def test_add_bookmark_default_label(self, controller):
        controller.addBookmark("")
        assert len(controller.bookmarks) == 1
        assert "Chapter 1" in controller.bookmarks[0]["label"]

    def test_add_bookmark_custom_label(self, controller):
        controller.addBookmark("My Bookmark")
        assert controller.bookmarks[0]["label"] == "My Bookmark"

    def test_add_bookmark_stores_position(self, controller):
        controller.goToChapter(1)
        controller.addBookmark("Bookmark at Ch 2")
        bm = controller.bookmarks[0]
        assert bm["chapter_index"] == 1

    def test_add_bookmark_emits_signal(self, controller):
        labels = []
        controller.bookmarkAdded.connect(lambda l: labels.append(l))
        controller.addBookmark("Test BM")
        assert "Test BM" in labels

    def test_multiple_bookmarks(self, controller):
        controller.addBookmark("BM1")
        controller.goToChapter(1)
        controller.addBookmark("BM2")
        controller.goToChapter(2)
        controller.addBookmark("BM3")
        assert len(controller.bookmarks) == 3


# --- Content and position tests ---


class TestEPUBReaderControllerContent:
    """Tests for content retrieval and position management."""

    def test_get_current_html(self, controller):
        html = controller.getCurrentHtml()
        assert "Chapter 1" in html
        assert "<style" in html  # CSS injected

    def test_get_current_html_empty_when_closed(self, empty_controller):
        html = empty_controller.getCurrentHtml()
        assert html == ""

    def test_content_ready_emitted_on_open(self, epub_file):
        ctrl = EPUBReaderController()
        content = []
        ctrl.contentReady.connect(lambda h: content.append(h))
        ctrl.openEpub(epub_file)
        assert len(content) == 1
        assert "Chapter 1" in content[0]
        ctrl.closeEpub()

    def test_content_ready_emitted_on_navigation(self, controller):
        content = []
        controller.contentReady.connect(lambda h: content.append(h))
        controller.goToChapter(1)
        assert len(content) >= 1
        assert "Chapter 2" in content[-1]

    def test_restore_position(self, controller):
        controller.restorePosition(2, 0.5)
        assert controller.currentChapter == 2
        pos = controller.bridge.get_reading_position()
        assert pos.chapter_index == 2
        assert pos.scroll_offset == 0.5

    def test_get_position_chapter(self, controller):
        controller.goToChapter(1)
        assert controller.getPositionChapter() == 1

    def test_get_position_offset(self, controller):
        # Default offset is 0.0
        assert controller.getPositionOffset() == 0.0


# --- Viewport tests ---


class TestEPUBReaderControllerViewport:
    """Tests for viewport management."""

    def test_set_viewport(self, controller):
        controller.setViewport(1024.0, 768.0)
        assert controller.backend.viewport_width == 1024
        assert controller.backend.viewport_height == 768

    def test_set_viewport_minimum(self, controller):
        controller.setViewport(10.0, 10.0)
        assert controller.backend.viewport_width == 100
        assert controller.backend.viewport_height == 100


# --- TOC model tests ---


class TestEPUBTocListModel:
    """Tests for the TOC list model."""

    def test_toc_model_row_count(self, controller):
        assert controller.tocModel.rowCount() == 3

    def test_toc_model_resolves_chapter_indices(self, controller):
        entries = controller.tocModel.get_entries()
        assert entries[0]["chapter_index"] == 0
        assert entries[1]["chapter_index"] == 1
        assert entries[2]["chapter_index"] == 2

    def test_toc_model_empty_when_closed(self, empty_controller):
        assert empty_controller.tocModel.rowCount() == 0


# --- Search result model tests ---


class TestEPUBSearchResultModel:
    """Tests for the search result model."""

    def test_model_initially_empty(self, controller):
        assert controller.searchModel.rowCount() == 0

    def test_model_populated_after_search(self, controller):
        controller.search("chapter")
        assert controller.searchModel.rowCount() > 0

    def test_model_cleared_on_empty_search(self, controller):
        controller.search("chapter")
        controller.search("")
        assert controller.searchModel.rowCount() == 0


# --- Resolve TOC href helper tests ---


class TestResolveTocHref:
    """Tests for the _resolve_toc_href_to_chapter helper."""

    def test_resolve_matching_href(self, controller):
        idx = _resolve_toc_href_to_chapter("chapter2.xhtml", controller.backend)
        assert idx == 1

    def test_resolve_with_fragment(self, controller):
        idx = _resolve_toc_href_to_chapter("chapter1.xhtml#section1", controller.backend)
        assert idx == 0

    def test_resolve_no_match(self, controller):
        idx = _resolve_toc_href_to_chapter("nonexistent.xhtml", controller.backend)
        assert idx == -1

    def test_resolve_empty_href(self, controller):
        idx = _resolve_toc_href_to_chapter("", controller.backend)
        assert idx == -1
