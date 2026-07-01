"""Unit tests for the PDF Reader Backend.

Tests cover:
- Zoom level clamping
- Page cache (LRU behavior, eviction, invalidation)
- View mode switching
- Page rendering and text extraction (with real PyMuPDF docs)
- Fit-width and fit-page presets
- Pre-rendering adjacent pages
- Continuous scroll visible pages calculation
"""

import fitz
import pytest

from src.infrastructure.readers.pdf_reader_backend import (
    DEFAULT_CACHE_SIZE,
    MAX_ZOOM,
    MIN_ZOOM,
    PRE_RENDER_RANGE,
    PageCache,
    PDFReaderBackend,
    RenderedPage,
    ViewMode,
    ZoomPreset,
    clamp_zoom,
)


# --- clamp_zoom tests ---


class TestClampZoom:
    """Tests for the clamp_zoom utility function."""

    def test_clamp_below_minimum(self):
        assert clamp_zoom(0.1) == MIN_ZOOM

    def test_clamp_above_maximum(self):
        assert clamp_zoom(5.0) == MAX_ZOOM

    def test_within_range_unchanged(self):
        assert clamp_zoom(1.5) == 1.5

    def test_at_minimum_boundary(self):
        assert clamp_zoom(MIN_ZOOM) == MIN_ZOOM

    def test_at_maximum_boundary(self):
        assert clamp_zoom(MAX_ZOOM) == MAX_ZOOM

    def test_zero_clamped_to_minimum(self):
        assert clamp_zoom(0.0) == MIN_ZOOM

    def test_negative_clamped_to_minimum(self):
        assert clamp_zoom(-1.0) == MIN_ZOOM

    def test_exactly_one(self):
        assert clamp_zoom(1.0) == 1.0


# --- PageCache tests ---


class TestPageCache:
    """Tests for the LRU page cache."""

    def _make_page(self, page_number: int, zoom: float = 1.0) -> RenderedPage:
        """Helper to create a RenderedPage with minimal data."""
        return RenderedPage(
            page_number=page_number,
            width=100,
            height=100,
            pixel_data=b"\x00" * 300,
            zoom_level=zoom,
        )

    def test_empty_cache_returns_none(self):
        cache = PageCache(max_size=5)
        assert cache.get(0, 1.0) is None

    def test_put_and_get(self):
        cache = PageCache(max_size=5)
        page = self._make_page(0, 1.0)
        cache.put(page)
        result = cache.get(0, 1.0)
        assert result is not None
        assert result.page_number == 0
        assert result.zoom_level == 1.0

    def test_different_zoom_levels_cached_separately(self):
        cache = PageCache(max_size=5)
        page1 = self._make_page(0, 1.0)
        page2 = self._make_page(0, 2.0)
        cache.put(page1)
        cache.put(page2)
        assert cache.get(0, 1.0) is not None
        assert cache.get(0, 2.0) is not None
        assert cache.get(0, 1.5) is None

    def test_lru_eviction(self):
        cache = PageCache(max_size=3)
        # Fill the cache
        cache.put(self._make_page(0))
        cache.put(self._make_page(1))
        cache.put(self._make_page(2))
        assert len(cache) == 3

        # Adding a 4th should evict page 0 (LRU)
        cache.put(self._make_page(3))
        assert len(cache) == 3
        assert cache.get(0, 1.0) is None
        assert cache.get(1, 1.0) is not None

    def test_access_refreshes_lru_order(self):
        cache = PageCache(max_size=3)
        cache.put(self._make_page(0))
        cache.put(self._make_page(1))
        cache.put(self._make_page(2))

        # Access page 0 to refresh it
        cache.get(0, 1.0)

        # Now page 1 is LRU; adding page 3 should evict page 1
        cache.put(self._make_page(3))
        assert cache.get(0, 1.0) is not None  # Refreshed, still present
        assert cache.get(1, 1.0) is None  # Evicted
        assert cache.get(2, 1.0) is not None

    def test_invalidate_all(self):
        cache = PageCache(max_size=5)
        cache.put(self._make_page(0))
        cache.put(self._make_page(1))
        cache.put(self._make_page(2))
        cache.invalidate()
        assert len(cache) == 0

    def test_invalidate_specific_page(self):
        cache = PageCache(max_size=5)
        cache.put(self._make_page(0, 1.0))
        cache.put(self._make_page(0, 2.0))
        cache.put(self._make_page(1, 1.0))
        cache.invalidate(page_number=0)
        assert cache.get(0, 1.0) is None
        assert cache.get(0, 2.0) is None
        assert cache.get(1, 1.0) is not None

    def test_contains(self):
        cache = PageCache(max_size=5)
        cache.put(self._make_page(0, 1.0))
        assert cache.contains(0, 1.0) is True
        assert cache.contains(0, 2.0) is False
        assert cache.contains(1, 1.0) is False

    def test_max_size_property(self):
        cache = PageCache(max_size=20)
        assert cache.max_size == 20

    def test_update_existing_entry(self):
        cache = PageCache(max_size=5)
        page1 = self._make_page(0, 1.0)
        page2 = RenderedPage(
            page_number=0,
            width=200,
            height=200,
            pixel_data=b"\xff" * 600,
            zoom_level=1.0,
        )
        cache.put(page1)
        cache.put(page2)
        assert len(cache) == 1
        result = cache.get(0, 1.0)
        assert result.width == 200


# --- PDFReaderBackend tests with real PyMuPDF doc ---


@pytest.fixture
def sample_pdf(tmp_path) -> str:
    """Create a simple multi-page PDF for testing."""
    doc = fitz.open()
    for i in range(10):
        page = doc.new_page(width=612, height=792)  # US Letter
        # Insert text on each page
        page.insert_text((72, 72), f"Page {i + 1} content", fontsize=12)
        page.insert_text((72, 100), f"This is sample text on page {i + 1}.", fontsize=10)
    path = str(tmp_path / "test.pdf")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def backend(sample_pdf) -> PDFReaderBackend:
    """Create a PDFReaderBackend with the sample PDF opened."""
    b = PDFReaderBackend(file_path=sample_pdf)
    yield b
    b.close()


class TestPDFReaderBackendBasic:
    """Basic backend operations."""

    def test_open_sets_page_count(self, backend: PDFReaderBackend):
        assert backend.page_count == 10

    def test_initial_state(self, backend: PDFReaderBackend):
        assert backend.current_page == 0
        assert backend.zoom_level == 1.0
        assert backend.zoom_preset == ZoomPreset.CUSTOM
        assert backend.view_mode == ViewMode.CONTINUOUS_SCROLL

    def test_close_resets_state(self, backend: PDFReaderBackend):
        backend.close()
        assert backend.page_count == 0
        assert backend.document is None

    def test_open_invalid_file_raises(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.pdf")
        with pytest.raises(RuntimeError, match="Failed to open PDF"):
            PDFReaderBackend(file_path=bad_path)

    def test_deferred_open(self, sample_pdf):
        b = PDFReaderBackend()
        assert b.page_count == 0
        b.open(sample_pdf)
        assert b.page_count == 10
        b.close()


class TestPDFReaderZoom:
    """Zoom level management."""

    def test_set_zoom_within_range(self, backend: PDFReaderBackend):
        result = backend.set_zoom(2.0)
        assert result == 2.0
        assert backend.zoom_level == 2.0

    def test_set_zoom_below_min_clamped(self, backend: PDFReaderBackend):
        result = backend.set_zoom(0.1)
        assert result == MIN_ZOOM
        assert backend.zoom_level == MIN_ZOOM

    def test_set_zoom_above_max_clamped(self, backend: PDFReaderBackend):
        result = backend.set_zoom(10.0)
        assert result == MAX_ZOOM
        assert backend.zoom_level == MAX_ZOOM

    def test_set_zoom_resets_preset_to_custom(self, backend: PDFReaderBackend):
        backend.set_zoom_fit_width()
        assert backend.zoom_preset == ZoomPreset.FIT_WIDTH
        backend.set_zoom(1.5)
        assert backend.zoom_preset == ZoomPreset.CUSTOM

    def test_fit_width(self, backend: PDFReaderBackend):
        backend.set_viewport(1224, 600)  # 2x the page width of 612
        zoom = backend.set_zoom_fit_width()
        assert abs(zoom - 2.0) < 0.01
        assert backend.zoom_preset == ZoomPreset.FIT_WIDTH

    def test_fit_page(self, backend: PDFReaderBackend):
        backend.set_viewport(612, 792)  # Exact page size
        zoom = backend.set_zoom_fit_page()
        assert abs(zoom - 1.0) < 0.01
        assert backend.zoom_preset == ZoomPreset.FIT_PAGE

    def test_fit_page_constrained_by_height(self, backend: PDFReaderBackend):
        # Viewport wider but shorter than page
        backend.set_viewport(1000, 396)  # Height is half of 792
        zoom = backend.set_zoom_fit_page()
        assert abs(zoom - 0.5) < 0.01

    def test_fit_width_clamped_at_max(self, backend: PDFReaderBackend):
        # Very wide viewport should clamp
        backend.set_viewport(100000, 600)
        zoom = backend.set_zoom_fit_width()
        assert zoom == MAX_ZOOM


class TestPDFReaderViewMode:
    """View mode switching."""

    def test_set_single_page_mode(self, backend: PDFReaderBackend):
        backend.set_view_mode(ViewMode.SINGLE_PAGE)
        assert backend.view_mode == ViewMode.SINGLE_PAGE

    def test_set_continuous_scroll_mode(self, backend: PDFReaderBackend):
        backend.set_view_mode(ViewMode.SINGLE_PAGE)
        backend.set_view_mode(ViewMode.CONTINUOUS_SCROLL)
        assert backend.view_mode == ViewMode.CONTINUOUS_SCROLL


class TestPDFReaderNavigation:
    """Page navigation."""

    def test_go_to_page(self, backend: PDFReaderBackend):
        result = backend.go_to_page(5)
        assert result == 5
        assert backend.current_page == 5

    def test_go_to_page_clamped_at_start(self, backend: PDFReaderBackend):
        result = backend.go_to_page(-5)
        assert result == 0

    def test_go_to_page_clamped_at_end(self, backend: PDFReaderBackend):
        result = backend.go_to_page(100)
        assert result == 9  # Last page (0-indexed)


class TestPDFReaderRendering:
    """Page rendering."""

    def test_render_page_returns_data(self, backend: PDFReaderBackend):
        rendered = backend.render_page(0)
        assert rendered.page_number == 0
        assert rendered.width > 0
        assert rendered.height > 0
        assert len(rendered.pixel_data) > 0
        assert rendered.zoom_level == 1.0

    def test_render_page_cached(self, backend: PDFReaderBackend):
        rendered1 = backend.render_page(0)
        rendered2 = backend.render_page(0)
        # Should return the same object from cache
        assert rendered1 is rendered2

    def test_render_page_different_zoom(self, backend: PDFReaderBackend):
        rendered_1x = backend.render_page(0, zoom=1.0)
        rendered_2x = backend.render_page(0, zoom=2.0)
        # 2x zoom should produce larger image
        assert rendered_2x.width > rendered_1x.width
        assert rendered_2x.height > rendered_1x.height

    def test_render_page_zoom_clamped(self, backend: PDFReaderBackend):
        rendered = backend.render_page(0, zoom=0.01)
        assert rendered.zoom_level == MIN_ZOOM

    def test_render_page_out_of_range_raises(self, backend: PDFReaderBackend):
        with pytest.raises(IndexError):
            backend.render_page(10)
        with pytest.raises(IndexError):
            backend.render_page(-1)

    def test_render_page_no_document_raises(self):
        b = PDFReaderBackend()
        with pytest.raises(RuntimeError, match="No document is open"):
            b.render_page(0)


class TestPDFReaderPreRender:
    """Pre-rendering adjacent pages."""

    def test_pre_render_caches_adjacent_pages(self, backend: PDFReaderBackend):
        backend.pre_render_adjacent(5)
        # Should cache pages 2-8 (5 ± 3)
        for page_num in range(2, 9):
            assert backend.cache.contains(page_num, 1.0), f"Page {page_num} not cached"

    def test_pre_render_respects_document_bounds(self, backend: PDFReaderBackend):
        # Near start
        backend.pre_render_adjacent(0)
        assert backend.cache.contains(0, 1.0)
        assert backend.cache.contains(1, 1.0)
        assert backend.cache.contains(2, 1.0)
        assert backend.cache.contains(3, 1.0)

    def test_pre_render_near_end(self, backend: PDFReaderBackend):
        backend.pre_render_adjacent(9)
        assert backend.cache.contains(6, 1.0)
        assert backend.cache.contains(9, 1.0)

    def test_pre_render_skips_already_cached(self, backend: PDFReaderBackend):
        # Pre-render once
        backend.render_page(5)
        initial_cache_size = len(backend.cache)
        # Pre-render again should not re-render page 5
        backend.pre_render_adjacent(5)
        # Cache should have pages 2-8 = 7 pages
        assert len(backend.cache) == 7


class TestPDFReaderTextExtraction:
    """Text extraction."""

    def test_extract_text_returns_content(self, backend: PDFReaderBackend):
        result = backend.extract_text(0)
        assert result.page_number == 0
        assert len(result.blocks) > 0
        # Check that our inserted text is found
        all_text = " ".join(b.text for b in result.blocks)
        assert "Page 1 content" in all_text

    def test_extract_text_has_position_info(self, backend: PDFReaderBackend):
        result = backend.extract_text(0)
        for block in result.blocks:
            assert block.x0 >= 0
            assert block.y0 >= 0
            assert block.x1 >= block.x0
            assert block.y1 >= block.y0

    def test_extract_text_raw_dict(self, backend: PDFReaderBackend):
        result = backend.extract_text(0)
        assert "blocks" in result.raw_dict

    def test_extract_text_out_of_range_raises(self, backend: PDFReaderBackend):
        with pytest.raises(IndexError):
            backend.extract_text(10)

    def test_extract_text_no_document_raises(self):
        b = PDFReaderBackend()
        with pytest.raises(RuntimeError, match="No document is open"):
            b.extract_text(0)


class TestPDFReaderPageSize:
    """Page size queries."""

    def test_get_page_size(self, backend: PDFReaderBackend):
        width, height = backend.get_page_size(0)
        assert abs(width - 612) < 0.01
        assert abs(height - 792) < 0.01

    def test_get_page_size_out_of_range_raises(self, backend: PDFReaderBackend):
        with pytest.raises(IndexError):
            backend.get_page_size(10)


class TestPDFReaderVisiblePages:
    """Visible page calculation."""

    def test_single_page_mode_returns_current(self, backend: PDFReaderBackend):
        backend.set_view_mode(ViewMode.SINGLE_PAGE)
        backend.go_to_page(3)
        visible = backend.get_visible_pages()
        assert visible == [3]

    def test_continuous_scroll_first_pages(self, backend: PDFReaderBackend):
        backend.set_view_mode(ViewMode.CONTINUOUS_SCROLL)
        backend.set_viewport(612, 792)  # Viewport = 1 page height at 1x zoom
        visible = backend.get_visible_pages(scroll_offset=0)
        assert 0 in visible
        # With viewport exactly one page, page 0 should be visible
        assert len(visible) >= 1

    def test_continuous_scroll_with_offset(self, backend: PDFReaderBackend):
        backend.set_view_mode(ViewMode.CONTINUOUS_SCROLL)
        backend.set_viewport(612, 792)
        # Scroll past first page (792px at zoom 1.0)
        visible = backend.get_visible_pages(scroll_offset=792)
        assert 0 not in visible
        assert 1 in visible

    def test_no_document_returns_empty(self):
        b = PDFReaderBackend()
        assert b.get_visible_pages() == []
