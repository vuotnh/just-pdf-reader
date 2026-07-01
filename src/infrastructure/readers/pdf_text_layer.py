"""PDF text layer generator for WebEngine overlay.

Generates HTML spans with per-character precision positioning using
PyMuPDF's rawdict output. Each character's exact bbox is used to
create absolutely positioned, transparent text that perfectly overlays
the rendered PDF image.

The approach:
1. Extract per-character bounding boxes from PyMuPDF rawdict
2. Group consecutive characters into word-level spans (split on spaces)
3. Position each word span at its first character's left/top
4. Set span width to exact pixel width (last char right - first char left)
5. Use JavaScript scaleX to stretch browser-rendered text to match exact width

This gives pixel-perfect text selection overlay at any zoom level.
"""

from __future__ import annotations

import html as html_module
from dataclasses import dataclass, field

import fitz


@dataclass
class WordSpan:
    """A word-level span with precise bbox from character data."""
    text: str
    left: float  # x0 of first char
    top: float   # y0 (top of bbox)
    width: float  # x1 of last char - x0 of first char
    height: float  # bbox height (consistent within a line)


def extract_word_spans(page: fitz.Page) -> list[WordSpan]:
    """Extract word-level spans with precise per-character bounding boxes.
    
    Uses rawdict to get per-character bbox, then groups chars into words.
    Each word span has pixel-perfect positioning data.
    
    Args:
        page: A PyMuPDF page object.
        
    Returns:
        List of WordSpan with precise positioning.
    """
    raw = page.get_text("rawdict")
    spans: list[WordSpan] = []

    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # text blocks only
            continue
        for line in block.get("lines", []):
            for span_data in line.get("spans", []):
                chars = span_data.get("chars", [])
                if not chars:
                    continue
                
                # Group chars into words (split on space chars)
                word_spans = _group_chars_to_words(chars)
                spans.extend(word_spans)

    return spans


def _group_chars_to_words(chars: list[dict]) -> list[WordSpan]:
    """Group character dicts into word-level spans.
    
    Splits on space characters. Each word gets the bbox from
    first char's left/top to last char's right/bottom.
    """
    words: list[WordSpan] = []
    current_chars: list[dict] = []

    for char in chars:
        c = char.get("c", "")
        if c == " " or c == "\t":
            # Flush current word
            if current_chars:
                words.append(_chars_to_span(current_chars))
                current_chars = []
            # Add space as its own span (needed for proper selection flow)
            words.append(WordSpan(
                text=" ",
                left=char["bbox"][0],
                top=char["bbox"][1],
                width=char["bbox"][2] - char["bbox"][0],
                height=char["bbox"][3] - char["bbox"][1],
            ))
        else:
            current_chars.append(char)

    # Flush last word
    if current_chars:
        words.append(_chars_to_span(current_chars))

    return words


def _chars_to_span(chars: list[dict]) -> WordSpan:
    """Convert a list of character dicts into a single WordSpan."""
    text = "".join(c.get("c", "") for c in chars)
    first_bbox = chars[0]["bbox"]
    last_bbox = chars[-1]["bbox"]
    
    return WordSpan(
        text=text,
        left=first_bbox[0],
        top=first_bbox[1],
        width=last_bbox[2] - first_bbox[0],
        height=first_bbox[3] - first_bbox[1],
    )


def generate_text_layer_html(page: fitz.Page, zoom: float = 1.0) -> str:
    """Generate HTML text layer spans for a PDF page.
    
    Each word is an absolutely positioned transparent <span> with
    data-w attribute for JavaScript scaleX adjustment.
    
    Args:
        page: PyMuPDF page object.
        zoom: Current zoom level multiplier.
        
    Returns:
        HTML string of all text spans.
    """
    word_spans = extract_word_spans(page)
    html_parts: list[str] = []

    for ws in word_spans:
        if not ws.text.strip():
            # Space spans: still include for selection continuity
            css_left = ws.left * zoom
            css_top = ws.top * zoom
            css_w = ws.width * zoom
            css_h = ws.height * zoom
            html_parts.append(
                f'<span style="left:{css_left:.1f}px;top:{css_top:.1f}px;'
                f'width:{css_w:.1f}px;height:{css_h:.1f}px;'
                f'font-size:{css_h:.1f}px;line-height:{css_h:.1f}px"> </span>'
            )
            continue

        css_left = ws.left * zoom
        css_top = ws.top * zoom
        css_w = ws.width * zoom
        css_h = ws.height * zoom
        fs = css_h  # font-size matches bbox height

        escaped = html_module.escape(ws.text)

        html_parts.append(
            f'<span data-w="{css_w:.2f}" style="'
            f'left:{css_left:.2f}px;'
            f'top:{css_top:.2f}px;'
            f'font-size:{fs:.2f}px;'
            f'line-height:{css_h:.2f}px;'
            f'height:{css_h:.2f}px'
            f'">{escaped}</span>'
        )

    return "\n".join(html_parts)
