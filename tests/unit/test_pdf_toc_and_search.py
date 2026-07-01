"""Unit tests for PDF TOC extraction and text search.

Tests cover:
- TOC extraction from PDF document outline (get_toc)
- Full-text search across all pages (search_text)
- Search result navigation via SearchNavigator (next/previous/go_to)
- Edge cases: empty documents, no TOC, no matches, wrap-around navigation
"""

import fitz
import pytest

from src.infrastructure.readers.pdf_reader_backend import (
    PDFReaderBackend,
    SearchMatch,
    SearchNavigator,
    TocEntry,
)


# --- Fixtures ---


@pytest.fixture
def pdf_with_toc(tmp_path) -> str:
    """Create a PDF with a table of contents (outline/bookmarks)."""
    doc = fitz.open()
    # Create pages with content
    for i in range(5):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Chapter {i + 1}", fontsize=16)
        page.insert_text((72, 120), f"Content for chapter {i + 1}.", fontsize=12)

    # Set table of contents
    # Format: [level, title, page_number (1-indexed)]
    toc = [
        [1, "Introduction", 1],
        [1, "Chapter 1: Getting Started", 2],
        [2, "Section 1.1: Setup", 2],
        [2, "Section 1.2: Configuration", 3],
        [1, "Chapter 2: Advanced Topics", 4],
        [2, "Section 2.1: Deep Dive", 4],
        [1, "Conclusion", 5],
    ]
    doc.set_toc(toc)

    path = str(tmp_path / "toc_test.pdf")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def pdf_without_toc(tmp_path) -> str:
    """Create a PDF without any table of contents."""
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Page {i + 1} without TOC", fontsize=12)
    path = str(tmp_path / "no_toc_test.pdf")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def pdf_with_searchable_text(tmp_path) -> str:
    """Create a PDF with known text content for search testing."""
    doc = fitz.open()

    # Page 0: has "hello" twice and "world" once
    page0 = doc.new_page(width=612, height=792)
    page0.insert_text((72, 72), "hello world hello", fontsize=12)
    page0.insert_text((72, 100), "This is a test document.", fontsize=12)

    # Page 1: has "hello" once and "python" once
    page1 = doc.new_page(width=612, height=792)
    page1.insert_text((72, 72), "hello from page two", fontsize=12)
    page1.insert_text((72, 100), "python programming is fun", fontsize=12)

    # Page 2: has "world" twice
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 72), "world of wonders", fontsize=12)
    page2.insert_text((72, 100), "another world awaits", fontsize=12)

    # Page 3: no relevant text
    page3 = doc.new_page(width=612, height=792)
    page3.insert_text((72, 72), "nothing special here", fontsize=12)

    path = str(tmp_path / "search_test.pdf")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def backend_with_toc(pdf_with_toc) -> PDFReaderBackend:
    """Backend with a TOC-enabled PDF."""
    b = PDFReaderBackend(file_path=pdf_with_toc)
    yield b
    b.close()


@pytest.fixture
def backend_without_toc(pdf_without_toc) -> PDFReaderBackend:
    """Backend with a no-TOC PDF."""
    b = PDFReaderBackend(file_path=pdf_without_toc)
    yield b
    b.close()


@pytest.fixture
def backend_searchable(pdf_with_searchable_text) -> PDFReaderBackend:
    """Backend with searchable text content."""
    b = PDFReaderBackend(file_path=pdf_with_searchable_text)
    yield b
    b.close()


# --- TOC Extraction Tests ---


class TestGetToc:
    """Tests for PDF TOC (Table of Contents) extraction."""

    def test_extracts_toc_entries(self, backend_with_toc: PDFReaderBackend):
        toc = backend_with_toc.get_toc()
        assert len(toc) == 7

    def test_toc_entry_structure(self, backend_with_toc: PDFReaderBackend):
        toc = backend_with_toc.get_toc()
        first = toc[0]
        assert isinstance(first, TocEntry)
        assert first.level == 1
        assert first.title == "Introduction"
        assert first.page_number == 0  # 0-indexed (was 1 in original)

    def test_toc_preserves_hierarchy(self, backend_with_toc: PDFReaderBackend):
        toc = backend_with_toc.get_toc()
        # Level 1 entries
        level1 = [e for e in toc if e.level == 1]
        assert len(level1) == 4
        # Level 2 entries
        level2 = [e for e in toc if e.level == 2]
        assert len(level2) == 3

    def test_toc_page_numbers_zero_indexed(self, backend_with_toc: PDFReaderBackend):
        toc = backend_with_toc.get_toc()
        # "Introduction" was on page 1 (1-indexed) -> page 0 (0-indexed)
        assert toc[0].page_number == 0
        # "Chapter 1" was on page 2 -> page 1
        assert toc[1].page_number == 1
        # "Conclusion" was on page 5 -> page 4
        assert toc[6].page_number == 4

    def test_toc_titles_correct(self, backend_with_toc: PDFReaderBackend):
        toc = backend_with_toc.get_toc()
        titles = [e.title for e in toc]
        assert "Introduction" in titles
        assert "Chapter 1: Getting Started" in titles
        assert "Section 1.1: Setup" in titles
        assert "Chapter 2: Advanced Topics" in titles
        assert "Conclusion" in titles

    def test_no_toc_returns_empty_list(self, backend_without_toc: PDFReaderBackend):
        toc = backend_without_toc.get_toc()
        assert toc == []

    def test_no_document_returns_empty_list(self):
        b = PDFReaderBackend()
        assert b.get_toc() == []


# --- Text Search Tests ---


class TestSearchText:
    """Tests for full-text search across all pages."""

    def test_finds_text_on_single_page(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("python")
        assert len(matches) == 1
        assert matches[0].page_number == 1

    def test_finds_text_across_multiple_pages(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("hello")
        # "hello" appears on page 0 (twice) and page 1 (once) = 3 total
        assert len(matches) == 3
        page_numbers = [m.page_number for m in matches]
        assert 0 in page_numbers
        assert 1 in page_numbers

    def test_search_match_structure(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("python")
        match = matches[0]
        assert isinstance(match, SearchMatch)
        assert match.page_number == 1
        assert match.text == "python"
        # Rect should have valid coordinates
        x0, y0, x1, y1 = match.rect
        assert x0 >= 0
        assert y0 >= 0
        assert x1 > x0
        assert y1 > y0

    def test_no_matches_returns_empty(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("nonexistent_xyz")
        assert matches == []

    def test_empty_query_returns_empty(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("")
        assert matches == []

    def test_no_document_returns_empty(self):
        b = PDFReaderBackend()
        assert b.search_text("hello") == []

    def test_search_is_case_insensitive_by_default(self, backend_searchable: PDFReaderBackend):
        matches_lower = backend_searchable.search_text("hello")
        matches_upper = backend_searchable.search_text("Hello")
        # Both should find the same occurrences (case-insensitive)
        assert len(matches_lower) == len(matches_upper)

    def test_search_results_ordered_by_page(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("world")
        # "world" on page 0, and page 2 (twice)
        page_numbers = [m.page_number for m in matches]
        assert page_numbers == sorted(page_numbers)

    def test_multiple_matches_on_same_page(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("world")
        # Page 2 has "world" twice
        page2_matches = [m for m in matches if m.page_number == 2]
        assert len(page2_matches) == 2

    def test_search_returns_bounding_rect(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("test")
        assert len(matches) >= 1
        for match in matches:
            x0, y0, x1, y1 = match.rect
            assert x1 > x0  # Width is positive
            assert y1 > y0  # Height is positive


# --- SearchNavigator Tests ---


class TestSearchNavigator:
    """Tests for search result navigation (next/previous/go_to)."""

    def _make_matches(self, count: int) -> list[SearchMatch]:
        """Helper to create a list of SearchMatch objects."""
        return [
            SearchMatch(
                page_number=i,
                text="test",
                rect=(10.0 * i, 10.0, 10.0 * i + 50.0, 20.0),
            )
            for i in range(count)
        ]

    def test_empty_navigator(self):
        nav = SearchNavigator()
        assert nav.match_count == 0
        assert nav.current_index == -1
        assert nav.current_match is None

    def test_init_with_matches(self):
        matches = self._make_matches(5)
        nav = SearchNavigator(matches=matches)
        assert nav.match_count == 5
        assert nav.current_index == 0
        assert nav.current_match == matches[0]

    def test_next_match_advances(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        # Initially at index 0, next goes to 1
        result = nav.next_match()
        assert result == matches[1]
        assert nav.current_index == 1

    def test_next_match_wraps_around(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        nav.next_match()  # -> 1
        nav.next_match()  # -> 2
        result = nav.next_match()  # -> 0 (wrap)
        assert result == matches[0]
        assert nav.current_index == 0

    def test_previous_match_goes_back(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        nav.next_match()  # -> 1
        nav.next_match()  # -> 2
        result = nav.previous_match()  # -> 1
        assert result == matches[1]
        assert nav.current_index == 1

    def test_previous_match_wraps_around(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        # At index 0, previous wraps to last
        result = nav.previous_match()
        assert result == matches[2]
        assert nav.current_index == 2

    def test_next_with_no_matches_returns_none(self):
        nav = SearchNavigator()
        assert nav.next_match() is None

    def test_previous_with_no_matches_returns_none(self):
        nav = SearchNavigator()
        assert nav.previous_match() is None

    def test_go_to_match_valid_index(self):
        matches = self._make_matches(5)
        nav = SearchNavigator(matches=matches)
        result = nav.go_to_match(3)
        assert result == matches[3]
        assert nav.current_index == 3

    def test_go_to_match_invalid_index_returns_none(self):
        matches = self._make_matches(5)
        nav = SearchNavigator(matches=matches)
        assert nav.go_to_match(-1) is None
        assert nav.go_to_match(5) is None
        assert nav.go_to_match(100) is None

    def test_go_to_match_empty_navigator(self):
        nav = SearchNavigator()
        assert nav.go_to_match(0) is None

    def test_set_matches_resets_to_first(self):
        nav = SearchNavigator()
        matches = self._make_matches(4)
        nav.set_matches(matches)
        assert nav.match_count == 4
        assert nav.current_index == 0
        assert nav.current_match == matches[0]

    def test_set_matches_with_empty_list(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        nav.set_matches([])
        assert nav.match_count == 0
        assert nav.current_index == -1
        assert nav.current_match is None

    def test_set_matches_replaces_previous(self):
        matches1 = self._make_matches(3)
        matches2 = self._make_matches(5)
        nav = SearchNavigator(matches=matches1)
        nav.next_match()  # Advance position
        nav.set_matches(matches2)
        # Should reset to first match of new list
        assert nav.current_index == 0
        assert nav.match_count == 5

    def test_matches_property_returns_all(self):
        matches = self._make_matches(3)
        nav = SearchNavigator(matches=matches)
        assert nav.matches == matches

    def test_single_match_navigation(self):
        matches = self._make_matches(1)
        nav = SearchNavigator(matches=matches)
        # Next should wrap to same match
        result = nav.next_match()
        assert result == matches[0]
        # Previous should also return same match
        result = nav.previous_match()
        assert result == matches[0]


# --- Integration: backend search + navigator ---


class TestSearchIntegration:
    """Integration tests combining backend search with navigator."""

    def test_search_and_navigate(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("hello")
        nav = SearchNavigator(matches=matches)
        assert nav.match_count == 3
        # Navigate through all matches
        first = nav.current_match
        assert first.page_number == 0
        second = nav.next_match()
        assert second is not None
        third = nav.next_match()
        assert third is not None
        # Wrap around
        wrapped = nav.next_match()
        assert wrapped == first

    def test_search_navigate_previous(self, backend_searchable: PDFReaderBackend):
        matches = backend_searchable.search_text("world")
        nav = SearchNavigator(matches=matches)
        # Previous from first wraps to last
        last = nav.previous_match()
        assert last == matches[-1]
