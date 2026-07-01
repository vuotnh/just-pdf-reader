"""Main application controller bridging Python backend to QML.

Renders PDF via WebEngineView with:
- High-res PNG background image (crisp rendering)  
- Transparent text overlay (native selection, copy, highlight)
- PDF.js-style approach: image for looks, invisible text for interaction
- Cambridge Dictionary lookup with popup display
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QMetaObject, Qt as QtConst, Q_ARG
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

import fitz  # PyMuPDF

from src.infrastructure.readers.pdf_text_layer import generate_text_layer_html
from src.infrastructure.readers.pdf_highlights_store import (
    add_highlight, load_highlights, get_page_highlights, remove_highlight, Highlight
)

logger = logging.getLogger(__name__)

# Render scale for crisp image (2x for HiDPI)
_RENDER_DPI = 144  # 2x of 72 DPI


class PDFImageProvider(QQuickImageProvider):
    """Unused fallback - kept for compatibility."""
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
    def requestImage(self, id, size, requestedSize):
        img = QImage(1, 1, QImage.Format.Format_RGB888)
        img.fill(0xFFFFFF)
        return img


class AppController(QObject):
    """Opens PDF and produces HTML with image bg + selectable text overlay."""

    # Signals
    bookOpened = Signal()
    bookClosed = Signal()
    pageChanged = Signal()
    zoomChanged = Signal()
    tocChanged = Signal()
    pageHtmlChanged = Signal()
    dictionaryResultReady = Signal(str)  # JSON result for dictionary popup
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._doc: fitz.Document | None = None
        self._file_path: str = ""
        self._current_page: int = 0
        self._page_count: int = 0
        self._book_title: str = ""
        self._book_format: str = ""
        self._zoom: float = 1.0
        self._toc_json: str = "[]"
        self._page_html: str = ""
        self._dict_result_json: str = ""

    # Properties
    @Property(int, notify=pageChanged)
    def currentPage(self) -> int:
        return self._current_page

    @Property(int, notify=bookOpened)
    def pageCount(self) -> int:
        return self._page_count

    @Property(str, notify=bookOpened)
    def bookTitle(self) -> str:
        return self._book_title

    @Property(str, notify=bookOpened)
    def bookFormat(self) -> str:
        return self._book_format

    @Property(bool, notify=bookOpened)
    def isBookOpen(self) -> bool:
        return self._doc is not None

    @Property(float, notify=zoomChanged)
    def zoomLevel(self) -> float:
        return self._zoom

    @Property(int, notify=zoomChanged)
    def zoomPercent(self) -> int:
        return int(self._zoom * 100)

    @Property(str, notify=tocChanged)
    def tocJson(self) -> str:
        return self._toc_json

    @Property(str, notify=pageHtmlChanged)
    def pageHtml(self) -> str:
        return self._page_html

    # Slots - Book
    @Slot(str)
    def openBook(self, file_path: str) -> None:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            self._open_pdf(file_path)
        else:
            self.errorOccurred.emit(f"Format '{ext}' not yet supported.")

    @Slot()
    def closeBook(self) -> None:
        if self._doc:
            self._doc.close()
            self._doc = None
        self._current_page = 0
        self._page_count = 0
        self._book_title = ""
        self._book_format = ""
        self._toc_json = "[]"
        self._page_html = ""
        self._zoom = 1.0
        self.bookClosed.emit()
        self.tocChanged.emit()
        self.pageHtmlChanged.emit()

    # Slots - Navigation
    @Slot(int)
    def goToPage(self, page: int) -> None:
        if not self._doc:
            return
        page = max(0, min(page, self._page_count - 1))
        if page != self._current_page:
            self._current_page = page
            self._update_page_html()
            self.pageChanged.emit()

    @Slot()
    def nextPage(self) -> None:
        self.goToPage(self._current_page + 1)

    @Slot()
    def previousPage(self) -> None:
        self.goToPage(self._current_page - 1)

    # Slots - Zoom
    @Slot(float)
    def setZoom(self, zoom: float) -> None:
        zoom = max(0.5, min(4.0, zoom))
        if abs(zoom - self._zoom) > 0.01:
            self._zoom = zoom
            self._update_page_html()
            self.zoomChanged.emit()

    @Slot()
    def zoomIn(self) -> None:
        self.setZoom(self._zoom + 0.25)

    @Slot()
    def zoomOut(self) -> None:
        self.setZoom(self._zoom - 0.25)

    @Slot()
    def zoomReset(self) -> None:
        self.setZoom(1.0)

    # ------------------------------------------------------------------
    # Slots - Highlights persistence
    # ------------------------------------------------------------------

    @Slot(str, str)
    def saveHighlight(self, color: str, text: str) -> None:
        """Save a highlight for the current page.
        
        Called from JS when user applies highlight via context menu.
        """
        if not self._file_path or not self._doc:
            return
        hl = add_highlight(self._file_path, self._current_page, color, text)
        logger.info("Highlight saved: page=%d, color=%s, text='%s'", self._current_page, color, text[:50])

    @Slot(str)
    def removeHighlightById(self, highlight_id: str) -> None:
        """Remove a highlight by its ID."""
        if not self._file_path:
            return
        remove_highlight(self._file_path, highlight_id)
        logger.info("Highlight removed: %s", highlight_id)

    # ------------------------------------------------------------------
    # Slots - Dictionary
    # ------------------------------------------------------------------

    @Property(str, notify=dictionaryResultReady)
    def dictResultJson(self) -> str:
        return self._dict_result_json

    @Slot(str)
    def lookupDictionary(self, word: str) -> None:
        """Look up a word — emit Cambridge URLs for QML WebView to load.

        Since Python requests are blocked by corporate firewall,
        we let QML's WebEngineView load Cambridge directly (uses system network).
        """
        word = word.strip()
        if not word:
            logger.warning("lookupDictionary called with empty word")
            return

        import urllib.parse
        encoded = urllib.parse.quote(word.lower())
        url_vi = f"https://dictionary.cambridge.org/dictionary/english-vietnamese/{encoded}"
        url_en = f"https://dictionary.cambridge.org/dictionary/english/{encoded}"

        self._dict_result_json = json.dumps({
            "word": word,
            "urls": {"en_vi": url_vi, "en_en": url_en},
            "mode": "webview",
        }, ensure_ascii=False)

        logger.info("Dictionary lookup for '%s':", word)
        logger.info("  EN-VI URL: %s", url_vi)
        logger.info("  EN-EN URL: %s", url_en)
        logger.info("  JSON emitted: %s", self._dict_result_json)
        print(f"[DICT] Lookup '{word}'")
        print(f"[DICT] EN-VI: {url_vi}")
        print(f"[DICT] EN-EN: {url_en}")
        print(f"[DICT] JSON: {self._dict_result_json}")

        self.dictionaryResultReady.emit(self._dict_result_json)

    @Slot()
    def _emitDictResult(self) -> None:
        """Unused — kept for compatibility."""
        pass

    # Private
    def _open_pdf(self, file_path: str) -> None:
        try:
            if self._doc:
                self._doc.close()
            self._doc = fitz.open(file_path)
            self._file_path = file_path
            self._page_count = self._doc.page_count
            self._current_page = 0
            self._book_title = Path(file_path).stem
            self._book_format = "PDF"

            toc_raw = self._doc.get_toc()
            self._toc_json = json.dumps(
                [{"title": t[1], "page": max(0, t[2] - 1), "level": t[0]} for t in toc_raw],
                ensure_ascii=False,
            )

            self._update_page_html()
            self.bookOpened.emit()
            self.pageChanged.emit()
            self.tocChanged.emit()
            self.zoomChanged.emit()
        except Exception as e:
            logger.exception("Failed to open PDF: %s", file_path)
            self.errorOccurred.emit(f"Failed to open: {e}")

    def _update_page_html(self) -> None:
        """Build HTML for current page with scroll-to-next behavior.
        
        Renders single page. Mouse wheel at bottom/top of page triggers next/prev.
        Keeps rendering fast and HTML size manageable.
        """
        if not self._doc:
            self._page_html = ""
            self.pageHtmlChanged.emit()
            return

        zoom = self._zoom
        page = self._doc[self._current_page]
        rect = page.rect
        css_w = rect.width * zoom
        css_h = rect.height * zoom

        # Render high-res PNG (1.5x for balance of quality and speed)
        render_scale = zoom * 1.5
        mat = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        png_b64 = base64.b64encode(png_bytes).decode("ascii")

        # Text layer
        text_spans_html = generate_text_layer_html(page, zoom)

        # Load saved highlights for this page and inject as JS data
        page_highlights = get_page_highlights(self._file_path, self._current_page)
        highlights_json = json.dumps([h.to_dict() for h in page_highlights], ensure_ascii=False)

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #4a4a4a;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px;
    min-height: 100vh;
    overflow-y: auto;
}}
.page {{
    position: relative;
    width: {css_w:.1f}px;
    height: {css_h:.1f}px;
    background: white;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    margin: 0 auto;
    overflow: hidden;
    animation: fadeIn 0.15s ease-in;
}}
@keyframes fadeIn {{
    from {{ opacity: 0.7; }}
    to {{ opacity: 1; }}
}}
.page-image {{
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
}}
.text-layer {{
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    line-height: 1.0;
}}
.text-layer span {{
    position: absolute;
    color: transparent;
    white-space: pre;
    cursor: text;
    transform-origin: left top;
    padding: 0; margin: 0; border: 0;
    font-family: serif;
    vertical-align: top;
    overflow: hidden;
}}
.text-layer span::selection {{
    background: rgba(26, 115, 232, 0.35);
    color: transparent;
}}
/* Context menu */
.context-menu {{
    display: none;
    position: fixed;
    z-index: 99999;
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    padding: 6px 0;
    min-width: 220px;
    font-family: -apple-system, 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #333333;
}}
.context-menu.visible {{ display: block !important; }}
.context-menu .menu-item {{
    padding: 8px 16px; cursor: pointer;
    display: flex; align-items: center; gap: 10px;
    color: #333; user-select: none;
}}
.context-menu .menu-item:hover {{ background-color: #e8f0fe; }}
.context-menu .menu-item .icon {{ font-size: 15px; width: 20px; text-align: center; }}
.context-menu .menu-item .label {{ flex: 1; }}
.context-menu .menu-item .shortcut {{ color: #999; font-size: 11px; }}
.context-menu .separator {{ height: 1px; background: #e8e8e8; margin: 4px 0; }}
.hl {{ color: transparent !important; border-radius: 2px; }}
.hl-yellow {{ background: rgba(255, 235, 59, 0.45) !important; }}
.hl-green {{ background: rgba(76, 175, 80, 0.35) !important; }}
.hl-blue {{ background: rgba(33, 150, 243, 0.35) !important; }}
.hl-pink {{ background: rgba(233, 30, 99, 0.3) !important; }}
/* Saved highlights applied to spans */
.hl-saved {{ color: transparent; }}
.hl-saved-yellow {{ background: rgba(255, 235, 59, 0.45); }}
.hl-saved-green {{ background: rgba(76, 175, 80, 0.35); }}
.hl-saved-blue {{ background: rgba(33, 150, 243, 0.35); }}
.hl-saved-pink {{ background: rgba(233, 30, 99, 0.3); }}
</style>
</head>
<body>
<div class="page">
    <img class="page-image" src="data:image/png;base64,{png_b64}">
    <div class="text-layer">
        {text_spans_html}
    </div>
</div>

<div class="context-menu" id="contextMenu">
    <div class="menu-item" data-action="highlight-yellow"><span class="icon">🟡</span><span class="label">Highlight Yellow</span></div>
    <div class="menu-item" data-action="highlight-green"><span class="icon">🟢</span><span class="label">Highlight Green</span></div>
    <div class="menu-item" data-action="highlight-blue"><span class="icon">🔵</span><span class="label">Highlight Blue</span></div>
    <div class="menu-item" data-action="highlight-pink"><span class="icon">🩷</span><span class="label">Highlight Pink</span></div>
    <div class="menu-item" data-action="remove-highlight"><span class="icon">✖</span><span class="label">Remove Highlight</span></div>
    <div class="separator"></div>
    <div class="menu-item" data-action="add-note"><span class="icon">📝</span><span class="label">Add Note</span></div>
    <div class="separator"></div>
    <div class="menu-item" data-action="dictionary"><span class="icon">📖</span><span class="label">Look Up Dictionary</span></div>
    <div class="menu-item" data-action="translate"><span class="icon">🌐</span><span class="label">Translate</span></div>
    <div class="separator"></div>
    <div class="menu-item" data-action="copy"><span class="icon">📋</span><span class="label">Copy</span><span class="shortcut">Ctrl+C</span></div>
</div>

<script>
// Scale text spans
window.addEventListener('load', function() {{
    document.querySelectorAll('.text-layer span[data-w]').forEach(function(span) {{
        var targetW = parseFloat(span.getAttribute('data-w'));
        var actualW = span.offsetWidth;
        if (actualW > 0 && targetW > 0) {{
            span.style.transform = 'scaleX(' + (targetW / actualW).toFixed(6) + ')';
        }}
    }});
    
    // Apply saved highlights
    var savedHighlights = {highlights_json};
    savedHighlights.forEach(function(hl) {{
        // Find spans that contain the highlighted text and mark them
        var spans = document.querySelectorAll('.text-layer span');
        var remainingText = hl.text;
        spans.forEach(function(span) {{
            var spanText = span.textContent;
            if (remainingText.length > 0 && remainingText.startsWith(spanText)) {{
                span.classList.add('hl-saved', 'hl-saved-' + hl.color);
                remainingText = remainingText.substring(spanText.length).trimStart();
            }} else if (remainingText.length > 0 && spanText.includes(remainingText.split(' ')[0])) {{
                span.classList.add('hl-saved', 'hl-saved-' + hl.color);
                remainingText = '';
            }}
        }});
    }});
}});

// Scroll wheel → next/prev page when at top/bottom
var scrollCooldown = false;
var scrollAccumulator = 0;
var scrollThreshold = 150; // pixels of accumulated scroll needed to change page

document.addEventListener('wheel', function(e) {{
    if (e.ctrlKey) return;
    
    var atBottom = (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 10;
    var atTop = window.scrollY <= 5;
    
    if (e.deltaY > 0 && atBottom) {{
        scrollAccumulator += Math.abs(e.deltaY);
        if (scrollAccumulator >= scrollThreshold && !scrollCooldown) {{
            scrollCooldown = true;
            scrollAccumulator = 0;
            console.log('NAV:next');
            setTimeout(function() {{ scrollCooldown = false; }}, 400);
        }}
    }} else if (e.deltaY < 0 && atTop) {{
        scrollAccumulator += Math.abs(e.deltaY);
        if (scrollAccumulator >= scrollThreshold && !scrollCooldown) {{
            scrollCooldown = true;
            scrollAccumulator = 0;
            console.log('NAV:prev');
            setTimeout(function() {{ scrollCooldown = false; }}, 400);
        }}
    }} else {{
        scrollAccumulator = 0;
    }}
}}, {{ passive: true }});

// Context menu
var contextMenu = document.getElementById('contextMenu');
var selectedText = '';
var selectionRange = null;

document.addEventListener('contextmenu', function(e) {{
    e.preventDefault();
    var sel = window.getSelection();
    if (sel && sel.toString().trim().length > 0) {{
        selectedText = sel.toString().trim();
        selectionRange = sel.getRangeAt(0);
        contextMenu.style.left = e.clientX + 'px';
        contextMenu.style.top = e.clientY + 'px';
        contextMenu.classList.add('visible');
        setTimeout(function() {{
            var rect = contextMenu.getBoundingClientRect();
            if (rect.right > window.innerWidth) contextMenu.style.left = (window.innerWidth - rect.width - 8) + 'px';
            if (rect.bottom > window.innerHeight) contextMenu.style.top = (window.innerHeight - rect.height - 8) + 'px';
        }}, 0);
    }} else {{
        contextMenu.classList.remove('visible');
    }}
}});

document.addEventListener('mousedown', function(e) {{
    if (!contextMenu.contains(e.target)) contextMenu.classList.remove('visible');
}});

contextMenu.addEventListener('click', function(e) {{
    var item = e.target.closest('.menu-item');
    if (!item) return;
    var action = item.getAttribute('data-action');
    contextMenu.classList.remove('visible');
    switch(action) {{
        case 'highlight-yellow': case 'highlight-green': case 'highlight-blue': case 'highlight-pink':
            applyHighlight(action.replace('highlight-', '')); break;
        case 'remove-highlight': removeHighlight(); break;
        case 'add-note': console.log('ACTION:add-note:' + selectedText); break;
        case 'dictionary': console.log('ACTION:dictionary:' + selectedText); break;
        case 'translate': console.log('ACTION:translate:' + selectedText); break;
        case 'copy': navigator.clipboard.writeText(selectedText); break;
    }}
}});

function applyHighlight(color) {{
    if (!selectionRange) return;
    try {{
        var mark = document.createElement('mark');
        mark.className = 'hl hl-' + color;
        var fragment = selectionRange.cloneRange().extractContents();
        mark.appendChild(fragment);
        selectionRange.insertNode(mark);
    }} catch(e) {{}}
    window.getSelection().removeAllRanges();
    // Persist highlight
    console.log('ACTION:highlight-' + color + ':' + selectedText);
    console.log('SAVE_HIGHLIGHT:' + color + ':' + selectedText);
}}

function removeHighlight() {{
    if (!selectionRange) return;
    var container = selectionRange.commonAncestorContainer;
    if (container.nodeType === 3) container = container.parentNode;
    var marks = container.querySelectorAll ? container.querySelectorAll('.hl') : [];
    marks.forEach(function(mark) {{
        if (selectionRange.intersectsNode(mark)) {{
            var parent = mark.parentNode;
            while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
            parent.removeChild(mark);
        }}
    }});
    window.getSelection().removeAllRanges();
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') contextMenu.classList.remove('visible');
}});
</script>
</body>
</html>"""

        self._page_html = html
        self.pageHtmlChanged.emit()
