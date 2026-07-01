"""Unit tests for the AnnotationController QML integration.

Tests the AnnotationController QObject including:
- Loading annotations for a book
- Text selection handling and context menu
- Highlight, underline, and note creation from selections
- Annotation deletion
- PDF overlay JSON generation
- EPUB CSS highlight injection generation
- Page and chapter annotation filtering
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.domain.enums import AnnotationType, HighlightColor
from src.domain.models import Annotation
from src.domain.value_objects import TextPosition
from src.presentation.controllers.annotation_controller import (
    AnnotationController,
    AnnotationListModel,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_annotation(
    ann_id: str = "ann-1",
    book_id: str = "book-1",
    ann_type: AnnotationType = AnnotationType.HIGHLIGHT,
    color: HighlightColor | None = HighlightColor.YELLOW,
    selected_text: str = "sample text",
    note_content: str | None = None,
    page: int | None = 5,
    chapter: str | None = None,
    start_offset: int = 10,
    end_offset: int = 20,
) -> Annotation:
    """Create a test annotation with position data."""
    from datetime import UTC, datetime

    position_data = json.dumps({
        "page": page,
        "chapter": chapter,
        "start_offset": start_offset,
        "end_offset": end_offset,
    })
    return Annotation(
        id=ann_id,
        book_id=book_id,
        type=ann_type,
        selected_text=selected_text,
        position_data=position_data,
        color=color,
        note_content=note_content,
        created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def mock_service():
    """Create a mock AnnotationService."""
    service = MagicMock()
    service.get_annotations.return_value = []
    service.create_annotation.return_value = _make_annotation()
    return service


@pytest.fixture
def controller(mock_service):
    """Create an AnnotationController with a mock service."""
    return AnnotationController(annotation_service=mock_service)


# ------------------------------------------------------------------
# AnnotationListModel tests
# ------------------------------------------------------------------


class TestAnnotationListModel:
    """Tests for the AnnotationListModel."""

    def test_empty_model(self):
        model = AnnotationListModel()
        assert model.rowCount() == 0

    def test_set_annotations(self):
        model = AnnotationListModel()
        annotations = [
            _make_annotation(ann_id="a1"),
            _make_annotation(ann_id="a2"),
        ]
        model.set_annotations(annotations)
        assert model.rowCount() == 2

    def test_data_id_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(ann_id="test-id")])

        from PySide6.QtCore import QModelIndex

        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.IdRole) == "test-id"

    def test_data_type_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(ann_type=AnnotationType.UNDERLINE)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.TypeRole) == "underline"

    def test_data_color_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(color=HighlightColor.GREEN)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.ColorRole) == "green"

    def test_data_color_role_none(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(color=None)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.ColorRole) == ""

    def test_data_selected_text_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(selected_text="hello world")])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.SelectedTextRole) == "hello world"

    def test_data_page_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(page=7)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.PageRole) == 7

    def test_data_page_role_none(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(page=None)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.PageRole) == -1

    def test_data_chapter_role(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(chapter="ch3")])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.ChapterRole) == "ch3"

    def test_data_chapter_role_none(self):
        model = AnnotationListModel()
        model.set_annotations([_make_annotation(chapter=None)])
        index = model.index(0, 0)
        assert model.data(index, AnnotationListModel.ChapterRole) == ""

    def test_data_invalid_index(self):
        model = AnnotationListModel()
        from PySide6.QtCore import QModelIndex

        index = model.index(99, 0)
        assert model.data(index, AnnotationListModel.IdRole) is None

    def test_role_names(self):
        model = AnnotationListModel()
        roles = model.roleNames()
        assert roles[AnnotationListModel.IdRole] == b"annotationId"
        assert roles[AnnotationListModel.TypeRole] == b"annotationType"
        assert roles[AnnotationListModel.ColorRole] == b"annotationColor"
        assert roles[AnnotationListModel.SelectedTextRole] == b"selectedText"


# ------------------------------------------------------------------
# AnnotationController tests
# ------------------------------------------------------------------


class TestAnnotationController:
    """Tests for the AnnotationController."""

    def test_initial_state(self, controller):
        assert controller.currentBookId == ""
        assert controller.selectedText == ""
        assert controller.contextMenuVisible is False
        assert controller.annotationCount == 0

    def test_load_annotations(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1"),
            _make_annotation(ann_id="a2"),
        ]

        controller.loadAnnotations("book-1")

        assert controller.currentBookId == "book-1"
        assert controller.annotationCount == 2
        mock_service.get_annotations.assert_called_once_with("book-1")

    def test_load_annotations_no_service(self):
        controller = AnnotationController(annotation_service=None)
        controller.loadAnnotations("book-1")
        assert controller.annotationCount == 0

    def test_on_text_selected(self, controller):
        controller.onTextSelected("hello", 3, "", 10, 15, 100.0, 200.0)

        assert controller.selectedText == "hello"
        assert controller.contextMenuVisible is True

    def test_dismiss_context_menu(self, controller):
        controller.onTextSelected("hello", 3, "", 10, 15, 100.0, 200.0)
        controller.dismissContextMenu()
        assert controller.contextMenuVisible is False

    def test_highlight_selection(self, controller, mock_service):
        controller.loadAnnotations("book-1")
        controller.onTextSelected("highlight me", 5, "", 0, 12, 100.0, 200.0)

        controller.highlightSelection("green")

        mock_service.create_annotation.assert_called_once()
        call_kwargs = mock_service.create_annotation.call_args
        assert call_kwargs[1]["ann_type"] == AnnotationType.HIGHLIGHT
        assert call_kwargs[1]["color"] == HighlightColor.GREEN
        assert call_kwargs[1]["book_id"] == "book-1"

    def test_highlight_selection_invalid_color_defaults_to_yellow(self, controller, mock_service):
        controller.loadAnnotations("book-1")
        controller.onTextSelected("text", 5, "", 0, 4, 100.0, 200.0)

        controller.highlightSelection("invalid_color")

        call_kwargs = mock_service.create_annotation.call_args
        assert call_kwargs[1]["color"] == HighlightColor.YELLOW

    def test_underline_selection(self, controller, mock_service):
        controller.loadAnnotations("book-1")
        controller.onTextSelected("underline me", 5, "", 0, 12, 100.0, 200.0)

        controller.underlineSelection()

        call_kwargs = mock_service.create_annotation.call_args
        assert call_kwargs[1]["ann_type"] == AnnotationType.UNDERLINE
        assert call_kwargs[1]["color"] is None

    def test_add_note_to_selection(self, controller, mock_service):
        controller.loadAnnotations("book-1")
        controller.onTextSelected("noted text", 5, "", 0, 10, 100.0, 200.0)

        controller.addNoteToSelection("This is my note")

        call_kwargs = mock_service.create_annotation.call_args
        assert call_kwargs[1]["ann_type"] == AnnotationType.NOTE
        assert call_kwargs[1]["content"] == "This is my note"

    def test_create_annotation_no_selection(self, controller, mock_service):
        """Should emit error when no text is selected."""
        controller.loadAnnotations("book-1")
        # Don't select any text
        error_emitted = []
        controller.errorOccurred.connect(error_emitted.append)

        controller.highlightSelection("yellow")

        assert len(error_emitted) == 1
        assert "No text selected" in error_emitted[0]
        mock_service.create_annotation.assert_not_called()

    def test_create_annotation_no_book(self, controller, mock_service):
        """Should emit error when no book is loaded."""
        controller.onTextSelected("text", 5, "", 0, 4, 100.0, 200.0)
        error_emitted = []
        controller.errorOccurred.connect(error_emitted.append)

        controller.highlightSelection("yellow")

        assert len(error_emitted) == 1
        assert "No book loaded" in error_emitted[0]

    def test_delete_annotation(self, controller, mock_service):
        controller.loadAnnotations("book-1")
        controller.deleteAnnotation("ann-1")

        mock_service.delete_annotation.assert_called_once_with("ann-1")

    def test_delete_annotation_not_found(self, controller, mock_service):
        mock_service.delete_annotation.side_effect = ValueError("not found")
        controller.loadAnnotations("book-1")

        error_emitted = []
        controller.errorOccurred.connect(error_emitted.append)

        controller.deleteAnnotation("nonexistent")
        assert len(error_emitted) == 1

    def test_add_comment(self, controller, mock_service):
        controller.addComment("ann-1", "great point")
        mock_service.add_comment.assert_called_once_with("ann-1", "great point")

    def test_add_tag(self, controller, mock_service):
        controller.addTag("ann-1", "important")
        mock_service.add_tag.assert_called_once_with("ann-1", "important")

    def test_export_annotations(self, controller, mock_service):
        mock_service.export_markdown.return_value = "# Annotations\n..."
        controller.loadAnnotations("book-1")

        export_received = []
        controller.exportReady.connect(export_received.append)

        controller.exportAnnotations()

        assert len(export_received) == 1
        assert export_received[0] == "# Annotations\n..."


# ------------------------------------------------------------------
# Reader Integration tests
# ------------------------------------------------------------------


class TestAnnotationControllerReaderIntegration:
    """Tests for PDF overlay and EPUB CSS integration."""

    def test_get_pdf_overlays(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1", page=3, start_offset=10, end_offset=20),
            _make_annotation(ann_id="a2", page=5, start_offset=0, end_offset=15),
        ]
        controller.loadAnnotations("book-1")

        overlays_json = controller.getPdfOverlays()
        overlays = json.loads(overlays_json)

        assert len(overlays) == 2
        assert overlays[0]["id"] == "a1"
        assert overlays[0]["page"] == 3
        assert overlays[0]["color"] == "yellow"
        assert overlays[1]["id"] == "a2"
        assert overlays[1]["page"] == 5

    def test_get_pdf_overlays_skips_epub_annotations(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1", page=3),
            _make_annotation(ann_id="a2", page=None, chapter="ch1"),
        ]
        controller.loadAnnotations("book-1")

        overlays_json = controller.getPdfOverlays()
        overlays = json.loads(overlays_json)

        # Only the PDF annotation (with page) should be included
        assert len(overlays) == 1
        assert overlays[0]["id"] == "a1"

    def test_get_epub_highlight_css(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(
                ann_id="a1",
                page=None,
                chapter="ch1",
                ann_type=AnnotationType.HIGHLIGHT,
                color=HighlightColor.BLUE,
            ),
        ]
        controller.loadAnnotations("book-1")

        css = controller.getEpubHighlightCss()

        # Should contain a CSS rule for the annotation
        ann_id_no_dash = "a1".replace("-", "")
        assert f".annotation-{ann_id_no_dash}" in css
        assert "background-color" in css
        assert "rgba(0, 150, 255, 0.25)" in css

    def test_get_epub_highlight_css_underline(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(
                ann_id="a2",
                page=None,
                chapter="ch2",
                ann_type=AnnotationType.UNDERLINE,
                color=None,
            ),
        ]
        controller.loadAnnotations("book-1")

        css = controller.getEpubHighlightCss()

        assert "border-bottom" in css
        assert "2px solid" in css

    def test_get_epub_highlight_css_skips_pdf_annotations(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1", page=5, chapter=None),
        ]
        controller.loadAnnotations("book-1")

        css = controller.getEpubHighlightCss()

        # PDF-only annotation should not generate EPUB CSS
        assert css == ""

    def test_get_page_annotations(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1", page=3),
            _make_annotation(ann_id="a2", page=5),
            _make_annotation(ann_id="a3", page=3),
        ]
        controller.loadAnnotations("book-1")

        result_json = controller.getPageAnnotations(3)
        result = json.loads(result_json)

        assert len(result) == 2
        assert result[0]["id"] == "a1"
        assert result[1]["id"] == "a3"

    def test_get_chapter_annotations(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(ann_id="a1", page=None, chapter="ch1"),
            _make_annotation(ann_id="a2", page=None, chapter="ch2"),
            _make_annotation(ann_id="a3", page=None, chapter="ch1"),
        ]
        controller.loadAnnotations("book-1")

        result_json = controller.getChapterAnnotations("ch1")
        result = json.loads(result_json)

        assert len(result) == 2
        assert result[0]["id"] == "a1"
        assert result[1]["id"] == "a3"

    def test_epub_css_note_type(self, controller, mock_service):
        mock_service.get_annotations.return_value = [
            _make_annotation(
                ann_id="n1",
                page=None,
                chapter="ch1",
                ann_type=AnnotationType.NOTE,
                color=None,
                note_content="A note",
            ),
        ]
        controller.loadAnnotations("book-1")

        css = controller.getEpubHighlightCss()

        assert "dashed" in css
        assert "background-color" in css
