"""QWebEngine Bridge for EPUB/AZW3 Reader.

Provides Python-side QObject that communicates with JavaScript running inside
QWebEngineView via QWebChannel. Handles:
- Text selection events (JS → Python)
- Annotation rendering (Python → JS)
- Font settings application
- Dark mode CSS injection (preserving image appearance)
- Reading position save/restore (chapter index + scroll offset)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot

from src.domain.enums import HighlightColor
from src.infrastructure.readers.epub_reader_backend import (
    FontSettings,
    clamp_font_size,
    MIN_FONT_SIZE,
    MAX_FONT_SIZE,
)


@dataclass
class ReadingPositionState:
    """Stores the current reading position for save/restore.

    Attributes:
        chapter_index: Current chapter (0-based index into the spine).
        scroll_offset: Vertical scroll offset as a fraction [0.0, 1.0].
    """

    chapter_index: int = 0
    scroll_offset: float = 0.0


# JavaScript to be injected into EPUB HTML pages for bridge communication.
# This script sets up QWebChannel, handles text selection events,
# provides annotation rendering, and manages scroll position.
BRIDGE_JAVASCRIPT = r"""
(function() {
    'use strict';

    // Wait for QWebChannel to be available
    if (typeof QWebChannel === 'undefined') {
        console.warn('QWebChannel not available');
        return;
    }

    new QWebChannel(qt.webChannelTransport, function(channel) {
        var bridge = channel.objects.bridge;
        if (!bridge) {
            console.warn('Bridge object not found in channel');
            return;
        }

        // --- Text Selection Handling ---
        document.addEventListener('mouseup', function(event) {
            var selection = window.getSelection();
            if (selection && selection.toString().trim().length > 0) {
                var range = selection.getRangeAt(0);
                var rect = range.getBoundingClientRect();
                bridge.onTextSelected(
                    selection.toString(),
                    range.startOffset,
                    range.endOffset,
                    rect.x,
                    rect.y,
                    rect.width,
                    rect.height
                );
            }
        });

        document.addEventListener('mousedown', function(event) {
            // Notify bridge when selection is cleared
            var selection = window.getSelection();
            if (selection && selection.toString().trim().length === 0) {
                bridge.onSelectionCleared();
            }
        });

        // --- Annotation Rendering ---
        window.addAnnotationHighlight = function(annotationId, startOffset, endOffset, color) {
            // Find text nodes and wrap the range with a highlight span
            var body = document.body;
            var walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null, false);
            var currentOffset = 0;
            var node;
            var rangesToHighlight = [];

            while (node = walker.nextNode()) {
                var nodeLength = node.textContent.length;
                var nodeStart = currentOffset;
                var nodeEnd = currentOffset + nodeLength;

                if (nodeEnd > startOffset && nodeStart < endOffset) {
                    var highlightStart = Math.max(0, startOffset - nodeStart);
                    var highlightEnd = Math.min(nodeLength, endOffset - nodeStart);
                    rangesToHighlight.push({
                        node: node,
                        start: highlightStart,
                        end: highlightEnd
                    });
                }
                currentOffset += nodeLength;
            }

            rangesToHighlight.forEach(function(item) {
                var range = document.createRange();
                range.setStart(item.node, item.start);
                range.setEnd(item.node, item.end);
                var span = document.createElement('span');
                span.className = 'annotation-highlight annotation-' + annotationId;
                span.dataset.annotationId = annotationId;
                span.style.backgroundColor = color;
                range.surroundContents(span);
            });
        };

        window.removeAnnotationHighlight = function(annotationId) {
            var spans = document.querySelectorAll('[data-annotation-id="' + annotationId + '"]');
            spans.forEach(function(span) {
                var parent = span.parentNode;
                while (span.firstChild) {
                    parent.insertBefore(span.firstChild, span);
                }
                parent.removeChild(span);
                parent.normalize();
            });
        };

        window.clearAllAnnotations = function() {
            var spans = document.querySelectorAll('.annotation-highlight');
            spans.forEach(function(span) {
                var parent = span.parentNode;
                while (span.firstChild) {
                    parent.insertBefore(span.firstChild, span);
                }
                parent.removeChild(span);
                parent.normalize();
            });
        };

        // --- Font Settings ---
        window.applyFontSettings = function(family, size, lineHeight) {
            var style = document.getElementById('bridge-font-style');
            if (!style) {
                style = document.createElement('style');
                style.id = 'bridge-font-style';
                document.head.appendChild(style);
            }
            style.textContent = 'body { font-family: ' + family + '; ' +
                'font-size: ' + size + 'pt; ' +
                'line-height: ' + lineHeight + '; }';
        };

        // --- Dark Mode ---
        window.applyDarkMode = function(enabled) {
            var style = document.getElementById('bridge-dark-mode-style');
            if (!style) {
                style = document.createElement('style');
                style.id = 'bridge-dark-mode-style';
                document.head.appendChild(style);
            }
            if (enabled) {
                style.textContent =
                    'body { background-color: #1a1a1a; color: #e0e0e0; } ' +
                    'a { color: #6db3f2; } ' +
                    'img, svg, video { filter: none; }';
            } else {
                style.textContent = '';
            }
        };

        // --- Reading Position ---
        window.getScrollPosition = function() {
            var scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
            var scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight;
            var clientHeight = document.documentElement.clientHeight || document.body.clientHeight;
            var maxScroll = scrollHeight - clientHeight;
            if (maxScroll <= 0) return 0.0;
            return scrollTop / maxScroll;
        };

        window.setScrollPosition = function(fraction) {
            var scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight;
            var clientHeight = document.documentElement.clientHeight || document.body.clientHeight;
            var maxScroll = scrollHeight - clientHeight;
            var targetScroll = Math.max(0, Math.min(1, fraction)) * maxScroll;
            window.scrollTo(0, targetScroll);
        };

        // Notify Python when scroll position changes (debounced)
        var scrollTimeout = null;
        window.addEventListener('scroll', function() {
            if (scrollTimeout) clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(function() {
                bridge.onScrollPositionChanged(window.getScrollPosition());
            }, 250);
        });

        // Signal that bridge is ready
        bridge.onBridgeReady();
    });
})();
"""


# Color mapping for highlight rendering in JavaScript
HIGHLIGHT_COLOR_MAP: dict[HighlightColor, str] = {
    HighlightColor.YELLOW: "rgba(255, 255, 0, 0.3)",
    HighlightColor.GREEN: "rgba(0, 255, 0, 0.3)",
    HighlightColor.BLUE: "rgba(0, 150, 255, 0.3)",
    HighlightColor.PINK: "rgba(255, 105, 180, 0.3)",
    HighlightColor.ORANGE: "rgba(255, 165, 0, 0.3)",
}


class WebEngineBridge(QObject):
    """Python-side bridge object exposed to JavaScript via QWebChannel.

    This QObject is registered with QWebChannel under the name 'bridge'.
    JavaScript calls slots on this object to notify Python of events,
    and Python calls methods that execute JavaScript in the web page.

    Signals (Python → QML/Controllers):
        textSelected: Emitted when user selects text in the web view.
        selectionCleared: Emitted when text selection is cleared.
        scrollPositionChanged: Emitted when scroll position changes.
        bridgeReady: Emitted when JS bridge initialization completes.

    Usage:
        bridge = WebEngineBridge()
        channel = QWebChannel()
        channel.registerObject("bridge", bridge)
        web_view.page().setWebChannel(channel)
        web_view.page().runJavaScript(BRIDGE_JAVASCRIPT)
    """

    # Signals emitted to Python controllers
    textSelected = Signal(str, int, int, float, float, float, float)
    selectionCleared = Signal()
    scrollPositionChanged = Signal(float)
    bridgeReady = Signal()
    annotationAdded = Signal(str)
    annotationRemoved = Signal(str)
    fontSettingsChanged = Signal(str, int, float)
    darkModeChanged = Signal(bool)
    readingPositionChanged = Signal(int, float)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the WebEngine bridge.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._font_settings = FontSettings()
        self._dark_mode = False
        self._reading_position = ReadingPositionState()
        self._selected_text = ""
        self._selection_start = 0
        self._selection_end = 0
        self._is_ready = False
        self._pending_annotations: list[dict[str, Any]] = []
        self._web_page: Any = None  # QWebEnginePage reference for JS execution

    # --- Properties ---

    @Property(str, notify=textSelected)
    def selectedText(self) -> str:
        """Currently selected text in the web view."""
        return self._selected_text

    @Property(int, notify=textSelected)
    def selectionStart(self) -> int:
        """Start offset of the current text selection."""
        return self._selection_start

    @Property(int, notify=textSelected)
    def selectionEnd(self) -> int:
        """End offset of the current text selection."""
        return self._selection_end

    @Property(bool, notify=bridgeReady)
    def isReady(self) -> bool:
        """Whether the JavaScript bridge is initialized and ready."""
        return self._is_ready

    @Property(int, notify=readingPositionChanged)
    def chapterIndex(self) -> int:
        """Current chapter index."""
        return self._reading_position.chapter_index

    @Property(float, notify=readingPositionChanged)
    def scrollOffset(self) -> float:
        """Current scroll offset as a fraction [0.0, 1.0]."""
        return self._reading_position.scroll_offset

    @Property(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:
        """Whether dark mode is enabled."""
        return self._dark_mode

    # --- Slots called from JavaScript ---

    @Slot(str, int, int, float, float, float, float)
    def onTextSelected(
        self,
        text: str,
        start_offset: int,
        end_offset: int,
        rect_x: float,
        rect_y: float,
        rect_width: float,
        rect_height: float,
    ) -> None:
        """Called by JavaScript when user selects text.

        Args:
            text: The selected text content.
            start_offset: Character start offset in the text node.
            end_offset: Character end offset in the text node.
            rect_x: X coordinate of selection bounding rect.
            rect_y: Y coordinate of selection bounding rect.
            rect_width: Width of selection bounding rect.
            rect_height: Height of selection bounding rect.
        """
        self._selected_text = text
        self._selection_start = start_offset
        self._selection_end = end_offset
        self.textSelected.emit(
            text, start_offset, end_offset, rect_x, rect_y, rect_width, rect_height
        )

    @Slot()
    def onSelectionCleared(self) -> None:
        """Called by JavaScript when text selection is cleared."""
        self._selected_text = ""
        self._selection_start = 0
        self._selection_end = 0
        self.selectionCleared.emit()

    @Slot(float)
    def onScrollPositionChanged(self, position: float) -> None:
        """Called by JavaScript when scroll position changes.

        Args:
            position: Scroll position as fraction [0.0, 1.0].
        """
        self._reading_position.scroll_offset = max(0.0, min(1.0, position))
        self.scrollPositionChanged.emit(self._reading_position.scroll_offset)
        self.readingPositionChanged.emit(
            self._reading_position.chapter_index,
            self._reading_position.scroll_offset,
        )

    @Slot()
    def onBridgeReady(self) -> None:
        """Called by JavaScript when QWebChannel bridge is initialized."""
        self._is_ready = True
        self.bridgeReady.emit()
        # Apply any pending state
        self._apply_pending_state()

    # --- Methods called from Python (execute JavaScript) ---

    def set_web_page(self, page: Any) -> None:
        """Set the QWebEnginePage for JavaScript execution.

        Args:
            page: The QWebEnginePage instance to run JS on.
        """
        self._web_page = page

    def add_annotation_highlight(
        self,
        annotation_id: str,
        start_offset: int,
        end_offset: int,
        color: HighlightColor,
    ) -> None:
        """Add a highlight annotation to the rendered content.

        Executes JavaScript to wrap the specified text range with a
        colored highlight span.

        Args:
            annotation_id: Unique identifier for the annotation.
            start_offset: Character start offset in the document body.
            end_offset: Character end offset in the document body.
            color: Highlight color to apply.
        """
        css_color = HIGHLIGHT_COLOR_MAP.get(color, "rgba(255, 255, 0, 0.3)")
        js = (
            f"window.addAnnotationHighlight("
            f"'{annotation_id}', {start_offset}, {end_offset}, '{css_color}');"
        )
        self._run_javascript(js)
        self._pending_annotations.append({
            "id": annotation_id,
            "start": start_offset,
            "end": end_offset,
            "color": color,
        })
        self.annotationAdded.emit(annotation_id)

    def remove_annotation_highlight(self, annotation_id: str) -> None:
        """Remove a highlight annotation from the rendered content.

        Args:
            annotation_id: The annotation to remove.
        """
        js = f"window.removeAnnotationHighlight('{annotation_id}');"
        self._run_javascript(js)
        self._pending_annotations = [
            a for a in self._pending_annotations if a["id"] != annotation_id
        ]
        self.annotationRemoved.emit(annotation_id)

    def clear_all_annotations(self) -> None:
        """Remove all annotation highlights from the rendered content."""
        self._run_javascript("window.clearAllAnnotations();")
        self._pending_annotations.clear()

    def apply_font_settings(self, settings: FontSettings) -> None:
        """Apply font settings to the rendered content.

        Font size is clamped to [8, 48] pt range.

        Args:
            settings: Font settings to apply.
        """
        size = clamp_font_size(settings.size)
        self._font_settings = FontSettings(
            family=settings.family,
            size=size,
            line_height=settings.line_height,
        )
        js = (
            f"window.applyFontSettings("
            f"'{settings.family}', {size}, {settings.line_height});"
        )
        self._run_javascript(js)
        self.fontSettingsChanged.emit(
            self._font_settings.family,
            self._font_settings.size,
            self._font_settings.line_height,
        )

    def apply_dark_mode(self, enabled: bool) -> None:
        """Apply or remove dark mode styling.

        Dark mode inverts content colors while preserving image appearance
        (images, SVG, and video elements keep filter: none).

        Args:
            enabled: Whether to enable dark mode.
        """
        self._dark_mode = enabled
        js = f"window.applyDarkMode({'true' if enabled else 'false'});"
        self._run_javascript(js)
        self.darkModeChanged.emit(enabled)

    def save_reading_position(self, chapter_index: int, scroll_offset: float) -> ReadingPositionState:
        """Save the current reading position.

        Args:
            chapter_index: Current chapter index (0-based).
            scroll_offset: Scroll offset as fraction [0.0, 1.0].

        Returns:
            The saved ReadingPositionState.
        """
        self._reading_position = ReadingPositionState(
            chapter_index=chapter_index,
            scroll_offset=max(0.0, min(1.0, scroll_offset)),
        )
        self.readingPositionChanged.emit(
            self._reading_position.chapter_index,
            self._reading_position.scroll_offset,
        )
        return self._reading_position

    def restore_reading_position(self, position: ReadingPositionState) -> None:
        """Restore a previously saved reading position.

        Sets the chapter index and scrolls to the saved offset.
        The chapter navigation should be handled by the reader controller;
        this method handles the scroll offset restoration.

        Args:
            position: The reading position to restore.
        """
        self._reading_position = ReadingPositionState(
            chapter_index=position.chapter_index,
            scroll_offset=max(0.0, min(1.0, position.scroll_offset)),
        )
        js = f"window.setScrollPosition({self._reading_position.scroll_offset});"
        self._run_javascript(js)
        self.readingPositionChanged.emit(
            self._reading_position.chapter_index,
            self._reading_position.scroll_offset,
        )

    def get_reading_position(self) -> ReadingPositionState:
        """Get the current reading position state.

        Returns:
            Current ReadingPositionState with chapter and scroll offset.
        """
        return ReadingPositionState(
            chapter_index=self._reading_position.chapter_index,
            scroll_offset=self._reading_position.scroll_offset,
        )

    def set_chapter_index(self, chapter_index: int) -> None:
        """Update the chapter index in the reading position.

        Called when navigation changes the current chapter.

        Args:
            chapter_index: The new chapter index (0-based).
        """
        self._reading_position.chapter_index = chapter_index
        self.readingPositionChanged.emit(
            self._reading_position.chapter_index,
            self._reading_position.scroll_offset,
        )

    def get_bridge_javascript(self) -> str:
        """Get the JavaScript code to inject into web pages.

        Returns:
            The complete bridge JavaScript that should be injected
            after the page loads.
        """
        return BRIDGE_JAVASCRIPT

    # --- Internal helpers ---

    def _run_javascript(self, js: str) -> None:
        """Execute JavaScript on the web page.

        If the web page is not set or bridge is not ready,
        the call is silently ignored.

        Args:
            js: JavaScript code to execute.
        """
        if self._web_page is not None:
            self._web_page.runJavaScript(js)

    def _apply_pending_state(self) -> None:
        """Re-apply font settings, dark mode, and annotations after bridge ready.

        Called when the bridge becomes ready to ensure all pending
        state is synchronized with the web page.
        """
        # Apply font settings
        self.apply_font_settings(self._font_settings)

        # Apply dark mode
        self.apply_dark_mode(self._dark_mode)

        # Re-apply annotations
        for ann in self._pending_annotations:
            css_color = HIGHLIGHT_COLOR_MAP.get(
                ann["color"], "rgba(255, 255, 0, 0.3)"
            )
            js = (
                f"window.addAnnotationHighlight("
                f"'{ann['id']}', {ann['start']}, {ann['end']}, '{css_color}');"
            )
            self._run_javascript(js)

        # Restore scroll position
        if self._reading_position.scroll_offset > 0.0:
            js = f"window.setScrollPosition({self._reading_position.scroll_offset});"
            self._run_javascript(js)
