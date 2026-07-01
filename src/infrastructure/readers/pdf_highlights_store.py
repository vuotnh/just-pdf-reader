"""Persistent storage for PDF highlights using JSON files.

Each PDF file's highlights are stored in:
  ~/.ai-ebook-reader/highlights/<sha256_prefix>.json

Structure per file:
{
    "file_path": "...",
    "file_hash": "...",
    "highlights": [
        {
            "id": "uuid",
            "page": 0,
            "color": "yellow",
            "text": "selected text",
            "spans": [{"left": 0, "top": 0, "width": 100, "height": 12}],
            "created_at": "2024-01-01T00:00:00"
        }
    ]
}
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HIGHLIGHTS_DIR = Path.home() / ".ai-ebook-reader" / "highlights"


@dataclass
class HighlightSpan:
    """Position of a highlighted word on the page."""
    left: float
    top: float
    width: float
    height: float


@dataclass
class Highlight:
    """A single highlight annotation."""
    id: str
    page: int
    color: str  # yellow, green, blue, pink
    text: str
    spans: list[HighlightSpan] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "page": self.page,
            "color": self.color,
            "text": self.text,
            "spans": [{"left": s.left, "top": s.top, "width": s.width, "height": s.height} for s in self.spans],
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Highlight":
        return Highlight(
            id=d.get("id", str(uuid.uuid4())),
            page=d.get("page", 0),
            color=d.get("color", "yellow"),
            text=d.get("text", ""),
            spans=[HighlightSpan(**s) for s in d.get("spans", [])],
            created_at=d.get("created_at", ""),
        )


def _file_hash(file_path: str) -> str:
    """Compute short hash of file path for storage key."""
    return hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]


def _store_path(file_path: str) -> Path:
    """Get the JSON store path for a given PDF file."""
    return _HIGHLIGHTS_DIR / f"{_file_hash(file_path)}.json"


def load_highlights(file_path: str) -> list[Highlight]:
    """Load all highlights for a PDF file.
    
    Args:
        file_path: Absolute path to the PDF file.
        
    Returns:
        List of Highlight objects, empty list if no highlights exist.
    """
    store = _store_path(file_path)
    if not store.exists():
        return []

    try:
        data = json.loads(store.read_text(encoding="utf-8"))
        return [Highlight.from_dict(h) for h in data.get("highlights", [])]
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load highlights for '%s': %s", file_path, e)
        return []


def save_highlights(file_path: str, highlights: list[Highlight]) -> None:
    """Save all highlights for a PDF file.
    
    Args:
        file_path: Absolute path to the PDF file.
        highlights: List of Highlight objects to persist.
    """
    _HIGHLIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    store = _store_path(file_path)

    data = {
        "file_path": file_path,
        "file_hash": _file_hash(file_path),
        "highlights": [h.to_dict() for h in highlights],
    }

    try:
        store.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved %d highlights for '%s'", len(highlights), file_path)
    except OSError as e:
        logger.error("Failed to save highlights for '%s': %s", file_path, e)


def add_highlight(file_path: str, page: int, color: str, text: str) -> Highlight:
    """Add a new highlight and persist immediately.
    
    Args:
        file_path: PDF file path.
        page: Page number (0-indexed).
        color: Highlight color (yellow, green, blue, pink).
        text: The highlighted text content.
        
    Returns:
        The created Highlight object.
    """
    highlights = load_highlights(file_path)
    
    hl = Highlight(
        id=str(uuid.uuid4()),
        page=page,
        color=color,
        text=text,
        created_at=datetime.now(UTC).isoformat(),
    )
    highlights.append(hl)
    save_highlights(file_path, highlights)
    return hl


def remove_highlight(file_path: str, highlight_id: str) -> bool:
    """Remove a highlight by ID and persist.
    
    Args:
        file_path: PDF file path.
        highlight_id: The highlight's UUID to remove.
        
    Returns:
        True if removed, False if not found.
    """
    highlights = load_highlights(file_path)
    before_count = len(highlights)
    highlights = [h for h in highlights if h.id != highlight_id]
    
    if len(highlights) < before_count:
        save_highlights(file_path, highlights)
        return True
    return False


def get_page_highlights(file_path: str, page: int) -> list[Highlight]:
    """Get highlights for a specific page.
    
    Args:
        file_path: PDF file path.
        page: Page number (0-indexed).
        
    Returns:
        List of highlights on that page.
    """
    all_hl = load_highlights(file_path)
    return [h for h in all_hl if h.page == page]
