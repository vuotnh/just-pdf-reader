"""AZW3 Reader Backend.

Converts AZW3 (Kindle) files to HTML using Calibre's ebook-convert subprocess,
then reuses the EPUB rendering pipeline (QWebEngine + CSS injection) for display.

Features:
- Calibre ebook-convert subprocess call (AZW3 → HTML)
- Conversion progress reporting via stdout parsing
- File-based conversion cache at ~/.ai-ebook-reader/cache/azw3/{hash}/
- Error handling for DRM-locked and corrupted files with descriptive messages
- Reuses EPUB rendering pipeline after conversion
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from src.infrastructure.readers.epub_reader_backend import (
    AnnotationHighlight,
    EPUBViewMode,
    FontSettings,
    SearchResult,
    TocEntry,
    clamp_font_size,
    generate_dark_mode_css,
    generate_font_css,
    generate_highlight_css,
    generate_pagination_css,
    generate_scroll_css,
)

logger = logging.getLogger(__name__)


# Default cache directory
DEFAULT_CACHE_DIR = Path.home() / ".ai-ebook-reader" / "cache" / "azw3"

# Calibre ebook-convert executable name
EBOOK_CONVERT_CMD = "ebook-convert"


class ConversionStatus(Enum):
    """Status of the AZW3 conversion process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class AZW3Error(Exception):
    """Base exception for AZW3 reader errors."""

    pass


class DRMError(AZW3Error):
    """Raised when an AZW3 file is DRM-locked and cannot be converted."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        super().__init__(
            f"Cannot open '{Path(file_path).name}': This file is protected by DRM "
            f"(Digital Rights Management). Please use a DRM-free version of this book."
        )


class CorruptedFileError(AZW3Error):
    """Raised when an AZW3 file is corrupted and cannot be parsed."""

    def __init__(self, file_path: str, details: str = "") -> None:
        self.file_path = file_path
        detail_msg = f" Details: {details}" if details else ""
        super().__init__(
            f"Cannot open '{Path(file_path).name}': The file appears to be corrupted "
            f"or is not a valid AZW3/KF8 file.{detail_msg}"
        )


class ConversionError(AZW3Error):
    """Raised when Calibre conversion fails for a non-DRM/non-corruption reason."""

    def __init__(self, file_path: str, details: str = "") -> None:
        self.file_path = file_path
        detail_msg = f" Details: {details}" if details else ""
        super().__init__(
            f"Failed to convert '{Path(file_path).name}' to HTML.{detail_msg}"
        )


class CalibreNotFoundError(AZW3Error):
    """Raised when Calibre's ebook-convert is not found on the system."""

    def __init__(self) -> None:
        super().__init__(
            "Calibre's 'ebook-convert' command was not found. "
            "Please install Calibre (https://calibre-ebook.com) and ensure "
            "it is available on your system PATH."
        )


@dataclass
class ConversionProgress:
    """Progress information during AZW3 conversion."""

    status: ConversionStatus = ConversionStatus.PENDING
    percent: int = 0
    message: str = ""


@dataclass
class ConversionResult:
    """Result of an AZW3 to HTML conversion."""

    success: bool
    output_dir: Path | None = None
    html_file: Path | None = None
    error_message: str = ""


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file for cache key generation.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def find_ebook_convert() -> str | None:
    """Find the Calibre ebook-convert executable on the system.

    Checks the system PATH and common installation locations.

    Returns:
        Full path to ebook-convert executable, or None if not found.
    """
    # Check PATH first
    path = shutil.which(EBOOK_CONVERT_CMD)
    if path:
        return path

    # Check common installation locations on Windows
    common_paths = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Calibre2" / "ebook-convert.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Calibre2" / "ebook-convert.exe",
        Path.home() / "AppData" / "Local" / "Calibre2" / "ebook-convert.exe",
    ]

    for candidate in common_paths:
        if candidate.exists():
            return str(candidate)

    return None


def _parse_progress_from_output(line: str) -> int | None:
    """Parse conversion progress percentage from Calibre stdout output.

    Calibre outputs progress lines like:
        "X% Converting input to HTML..."
        "X% Running transforms..."

    Args:
        line: A line of stdout output from ebook-convert.

    Returns:
        Progress percentage (0-100) if the line contains progress info, else None.
    """
    match = re.match(r"^\s*(\d+)%", line.strip())
    if match:
        return int(match.group(1))
    return None


def _detect_drm_error(output: str) -> bool:
    """Detect DRM-related errors in Calibre conversion output.

    Args:
        output: Combined stdout/stderr from the conversion process.

    Returns:
        True if the output indicates a DRM-locked file.
    """
    drm_indicators = [
        "DRM",
        "drm",
        "Digital Rights Management",
        "encrypted",
        "DeDRM",
        "This book is locked by DRM",
        "Could not decrypt",
    ]
    return any(indicator in output for indicator in drm_indicators)


def _detect_corruption_error(output: str) -> bool:
    """Detect file corruption errors in Calibre conversion output.

    Args:
        output: Combined stdout/stderr from the conversion process.

    Returns:
        True if the output indicates a corrupted file.
    """
    corruption_indicators = [
        "not a valid",
        "corrupt",
        "malformed",
        "Invalid file",
        "Failed to parse",
        "could not be opened",
        "Traceback",
        "struct.error",
    ]
    output_lower = output.lower()
    return any(indicator.lower() in output_lower for indicator in corruption_indicators)


class ConversionCache:
    """File-based cache for AZW3 to HTML conversions.

    Stores converted HTML output in ~/.ai-ebook-reader/cache/azw3/{hash}/
    to avoid re-converting files on subsequent opens.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize the conversion cache.

        Args:
            cache_dir: Base directory for cached conversions.
                      Defaults to ~/.ai-ebook-reader/cache/azw3/
        """
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR

    @property
    def cache_dir(self) -> Path:
        """Base directory for cached conversions."""
        return self._cache_dir

    def get_cache_path(self, file_hash: str) -> Path:
        """Get the cache directory path for a given file hash.

        Args:
            file_hash: SHA-256 hash of the source AZW3 file.

        Returns:
            Path to the cache directory for this file.
        """
        return self._cache_dir / file_hash

    def has_cached(self, file_hash: str) -> bool:
        """Check if a converted version exists in the cache.

        Args:
            file_hash: SHA-256 hash of the source AZW3 file.

        Returns:
            True if a valid cached conversion exists.
        """
        cache_path = self.get_cache_path(file_hash)
        if not cache_path.exists():
            return False
        # Check that the HTML output file exists
        html_file = self._find_html_file(cache_path)
        return html_file is not None

    def get_cached_html_path(self, file_hash: str) -> Path | None:
        """Get the path to the cached HTML file.

        Args:
            file_hash: SHA-256 hash of the source AZW3 file.

        Returns:
            Path to the HTML file, or None if not cached.
        """
        cache_path = self.get_cache_path(file_hash)
        if not cache_path.exists():
            return None
        return self._find_html_file(cache_path)


    def prepare_cache_dir(self, file_hash: str) -> Path:
        """Create the cache directory for a file if it doesn't exist.

        Args:
            file_hash: SHA-256 hash of the source AZW3 file.

        Returns:
            Path to the (possibly newly created) cache directory.
        """
        cache_path = self.get_cache_path(file_hash)
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path

    def invalidate(self, file_hash: str) -> None:
        """Remove cached conversion for a file.

        Args:
            file_hash: SHA-256 hash of the source AZW3 file.
        """
        cache_path = self.get_cache_path(file_hash)
        if cache_path.exists():
            shutil.rmtree(cache_path, ignore_errors=True)

    def clear_all(self) -> None:
        """Remove all cached conversions."""
        if self._cache_dir.exists():
            shutil.rmtree(self._cache_dir, ignore_errors=True)
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _find_html_file(self, cache_path: Path) -> Path | None:
        """Find the main HTML file in a cache directory.

        Calibre produces an HTML file with the same base name as the input.

        Args:
            cache_path: The cache directory to search.

        Returns:
            Path to the HTML file, or None if not found.
        """
        html_files = list(cache_path.glob("*.html")) + list(cache_path.glob("*.htm"))
        if html_files:
            # Prefer index.html if it exists
            for hf in html_files:
                if hf.stem.lower() == "index":
                    return hf
            return html_files[0]
        return None


class AZW3Converter:
    """Handles the AZW3 to HTML conversion using Calibre's ebook-convert.

    Manages subprocess execution, progress parsing, and error detection.
    """

    def __init__(self, cache: ConversionCache | None = None) -> None:
        """Initialize the converter.

        Args:
            cache: Conversion cache instance. Creates a default one if not provided.
        """
        self._cache = cache or ConversionCache()
        self._ebook_convert_path: str | None = None
        self._progress_callback: Callable[[ConversionProgress], None] | None = None

    @property
    def cache(self) -> ConversionCache:
        """The conversion cache instance."""
        return self._cache

    def set_progress_callback(
        self, callback: Callable[[ConversionProgress], None] | None
    ) -> None:
        """Set a callback for conversion progress updates.

        Args:
            callback: Function to call with ConversionProgress updates.
                     Set to None to disable progress reporting.
        """
        self._progress_callback = callback

    def _report_progress(self, status: ConversionStatus, percent: int, message: str) -> None:
        """Report progress via the callback if set.

        Args:
            status: Current conversion status.
            percent: Progress percentage (0-100).
            message: Human-readable progress message.
        """
        if self._progress_callback:
            self._progress_callback(
                ConversionProgress(status=status, percent=percent, message=message)
            )

    def _ensure_calibre_available(self) -> str:
        """Ensure Calibre's ebook-convert is available.

        Returns:
            Path to the ebook-convert executable.

        Raises:
            CalibreNotFoundError: If ebook-convert cannot be found.
        """
        if self._ebook_convert_path is None:
            self._ebook_convert_path = find_ebook_convert()
        if self._ebook_convert_path is None:
            raise CalibreNotFoundError()
        return self._ebook_convert_path


    def convert(self, file_path: str) -> ConversionResult:
        """Convert an AZW3 file to HTML.

        Uses the cache if a previous conversion exists. Otherwise invokes
        Calibre's ebook-convert to produce HTML output.

        Args:
            file_path: Path to the AZW3 file.

        Returns:
            ConversionResult with output paths on success.

        Raises:
            FileNotFoundError: If the AZW3 file does not exist.
            CalibreNotFoundError: If ebook-convert is not available.
            DRMError: If the file is DRM-locked.
            CorruptedFileError: If the file is corrupted.
            ConversionError: If the conversion fails for another reason.
        """
        source_path = Path(file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"AZW3 file not found: {file_path}")

        # Compute file hash for cache lookup
        file_hash = compute_file_hash(file_path)

        # Check cache first
        if self._cache.has_cached(file_hash):
            html_path = self._cache.get_cached_html_path(file_hash)
            self._report_progress(
                ConversionStatus.CACHED, 100, "Using cached conversion"
            )
            return ConversionResult(
                success=True,
                output_dir=self._cache.get_cache_path(file_hash),
                html_file=html_path,
            )

        # Ensure Calibre is available
        ebook_convert = self._ensure_calibre_available()

        # Prepare output directory
        output_dir = self._cache.prepare_cache_dir(file_hash)
        output_file = output_dir / (source_path.stem + ".html")

        # Report start
        self._report_progress(
            ConversionStatus.IN_PROGRESS, 0, "Starting conversion..."
        )

        # Run ebook-convert
        try:
            result = self._run_ebook_convert(
                ebook_convert, str(source_path), str(output_file)
            )
        except Exception as e:
            # Clean up failed conversion
            self._cache.invalidate(file_hash)
            self._report_progress(
                ConversionStatus.FAILED, 0, str(e)
            )
            raise

        if not result.success:
            self._cache.invalidate(file_hash)
            self._report_progress(
                ConversionStatus.FAILED, 0, result.error_message
            )
            raise ConversionError(file_path, result.error_message)

        # Verify output exists
        html_path = self._cache.get_cached_html_path(file_hash)
        if html_path is None:
            self._cache.invalidate(file_hash)
            error_msg = "Conversion completed but no HTML output was produced"
            self._report_progress(ConversionStatus.FAILED, 0, error_msg)
            raise ConversionError(file_path, error_msg)

        self._report_progress(
            ConversionStatus.COMPLETED, 100, "Conversion complete"
        )
        return ConversionResult(
            success=True,
            output_dir=output_dir,
            html_file=html_path,
        )


    def _run_ebook_convert(
        self, ebook_convert: str, input_path: str, output_path: str
    ) -> ConversionResult:
        """Execute ebook-convert subprocess and parse output.

        Args:
            ebook_convert: Path to the ebook-convert executable.
            input_path: Path to the source AZW3 file.
            output_path: Path for the output HTML file.

        Returns:
            ConversionResult indicating success or failure.

        Raises:
            DRMError: If DRM is detected in the output.
            CorruptedFileError: If corruption is detected in the output.
        """
        cmd = [
            ebook_convert,
            input_path,
            output_path,
            "--no-images",  # Skip images initially for faster conversion
        ]

        # Remove --no-images to preserve images in conversion
        cmd = [
            ebook_convert,
            input_path,
            output_path,
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as e:
            raise CalibreNotFoundError() from e

        output_lines: list[str] = []
        last_percent = 0

        # Parse stdout for progress
        for line in iter(process.stdout.readline, ""):
            output_lines.append(line)
            progress = _parse_progress_from_output(line)
            if progress is not None and progress > last_percent:
                last_percent = progress
                self._report_progress(
                    ConversionStatus.IN_PROGRESS,
                    progress,
                    line.strip(),
                )

        process.wait()
        full_output = "".join(output_lines)

        # Check for errors
        if process.returncode != 0:
            if _detect_drm_error(full_output):
                raise DRMError(input_path)
            if _detect_corruption_error(full_output):
                raise CorruptedFileError(input_path, full_output[:200])
            return ConversionResult(
                success=False,
                error_message=f"ebook-convert exited with code {process.returncode}: "
                f"{full_output[:500]}",
            )

        return ConversionResult(success=True, output_dir=Path(output_path).parent)


class AZW3ReaderBackend:
    """Backend for reading AZW3 (Kindle) documents.

    Converts AZW3 files to HTML via Calibre, then provides an HTML rendering
    pipeline similar to the EPUB reader (QWebEngine + CSS injection).

    Provides:
    - AZW3 → HTML conversion via Calibre ebook-convert
    - File-based conversion cache (avoids re-conversion on subsequent opens)
    - Progress reporting during conversion
    - Error handling for DRM-locked and corrupted files
    - CSS injection for font settings, theme (dark mode), and annotation highlights
    - Pagination mode (CSS column splitting) and continuous scroll mode
    - Text search across converted HTML content
    """

    def __init__(
        self,
        file_path: str | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        """Initialize the AZW3 reader backend.

        Args:
            file_path: Path to the AZW3 file to open. Can be None for deferred open.
            cache_dir: Custom cache directory. Defaults to ~/.ai-ebook-reader/cache/azw3/
        """
        self._file_path: str | None = None
        self._file_hash: str | None = None
        self._converter = AZW3Converter(cache=ConversionCache(cache_dir))
        self._html_file: Path | None = None
        self._output_dir: Path | None = None
        self._html_content: str = ""
        self._view_mode: EPUBViewMode = EPUBViewMode.CONTINUOUS_SCROLL
        self._font_settings: FontSettings = FontSettings()
        self._dark_mode: bool = False
        self._highlights: list[AnnotationHighlight] = []
        self._viewport_width: int = 800
        self._viewport_height: int = 600
        self._toc: list[TocEntry] = []
        self._progress_callback: Callable[[ConversionProgress], None] | None = None

        if file_path:
            self.open(file_path)

    @property
    def file_path(self) -> str | None:
        """Path to the currently open AZW3 file."""
        return self._file_path

    @property
    def file_hash(self) -> str | None:
        """SHA-256 hash of the current AZW3 file."""
        return self._file_hash

    @property
    def html_file(self) -> Path | None:
        """Path to the converted HTML file."""
        return self._html_file

    @property
    def output_dir(self) -> Path | None:
        """Directory containing converted HTML and resources."""
        return self._output_dir


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
    def toc(self) -> list[TocEntry]:
        """Table of contents extracted from converted HTML."""
        return self._toc

    @property
    def viewport_width(self) -> int:
        """Current viewport width in pixels."""
        return self._viewport_width

    @property
    def viewport_height(self) -> int:
        """Current viewport height in pixels."""
        return self._viewport_height

    @property
    def converter(self) -> AZW3Converter:
        """The underlying AZW3 converter instance."""
        return self._converter

    def set_progress_callback(
        self, callback: Callable[[ConversionProgress], None] | None
    ) -> None:
        """Set a callback for conversion progress updates.

        The callback receives ConversionProgress objects with status,
        percent (0-100), and a human-readable message.

        Args:
            callback: Progress callback function, or None to disable.
        """
        self._progress_callback = callback
        self._converter.set_progress_callback(callback)

    def open(self, file_path: str) -> None:
        """Open an AZW3 file, converting it to HTML if not cached.

        This triggers the conversion pipeline:
        1. Compute file hash
        2. Check cache for existing conversion
        3. If not cached, invoke Calibre ebook-convert
        4. Load the resulting HTML

        Args:
            file_path: Path to the AZW3 file.

        Raises:
            FileNotFoundError: If the file does not exist.
            CalibreNotFoundError: If ebook-convert is not available.
            DRMError: If the file is DRM-locked.
            CorruptedFileError: If the file is corrupted.
            ConversionError: If conversion fails.
        """
        # Convert AZW3 to HTML
        result = self._converter.convert(file_path)

        self._file_path = file_path
        self._file_hash = compute_file_hash(file_path)
        self._html_file = result.html_file
        self._output_dir = result.output_dir

        # Load HTML content
        if self._html_file and self._html_file.exists():
            self._html_content = self._html_file.read_text(encoding="utf-8", errors="replace")

        # Extract TOC from HTML headings
        self._toc = self._extract_toc_from_html()


    def close(self) -> None:
        """Close the reader and release resources."""
        self._file_path = None
        self._file_hash = None
        self._html_file = None
        self._output_dir = None
        self._html_content = ""
        self._toc = []

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
            mode: The desired view mode (paginated or continuous scroll).
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


    def get_html(self) -> str:
        """Get the converted HTML content with CSS injection.

        Returns the HTML from the converted AZW3 file with injected CSS
        for font settings, theme, highlights, and view mode. This is
        analogous to the EPUB reader's get_chapter_html().

        Returns:
            Full HTML string with injected CSS.

        Raises:
            RuntimeError: If no AZW3 file is open.
        """
        if not self._html_content:
            raise RuntimeError("No AZW3 file is open")

        injected_css = self._build_injected_css()
        return self._inject_css_into_html(self._html_content, injected_css)

    def get_raw_html(self) -> str:
        """Get the raw converted HTML content without CSS injection.

        Returns:
            Raw HTML string from the conversion.

        Raises:
            RuntimeError: If no AZW3 file is open.
        """
        if not self._html_content:
            raise RuntimeError("No AZW3 file is open")
        return self._html_content

    def search_text(self, query: str) -> list[SearchResult]:
        """Search for text in the converted HTML content.

        Performs a case-insensitive search across the converted content,
        reusing the same SearchResult format as the EPUB reader.

        Args:
            query: The text to search for. Empty queries return no results.

        Returns:
            List of SearchResult objects with match positions.

        Raises:
            RuntimeError: If no AZW3 file is open.
        """
        if not self._html_content:
            raise RuntimeError("No AZW3 file is open")

        if not query or not query.strip():
            return []

        results: list[SearchResult] = []
        query_lower = query.lower()
        context_chars = 40

        plain_text = self._strip_html_tags(self._html_content)
        text_lower = plain_text.lower()

        start = 0
        while True:
            pos = text_lower.find(query_lower, start)
            if pos == -1:
                break

            context_start = max(0, pos - context_chars)
            context_end = min(len(plain_text), pos + len(query) + context_chars)
            match_text = plain_text[context_start:context_end]

            if context_start > 0:
                match_text = "..." + match_text
            if context_end < len(plain_text):
                match_text = match_text + "..."

            results.append(SearchResult(
                chapter_index=0,  # AZW3 is a single HTML file
                match_text=match_text,
                offset=pos,
            ))

            start = pos + 1

        return results


    def get_resource(self, resource_path: str) -> bytes:
        """Get a resource (image, CSS) from the conversion output directory.

        Args:
            resource_path: Path to the resource relative to the output directory.

        Returns:
            Raw bytes of the resource.

        Raises:
            RuntimeError: If no AZW3 file is open.
            FileNotFoundError: If the resource is not found.
        """
        if self._output_dir is None:
            raise RuntimeError("No AZW3 file is open")

        full_path = self._output_dir / resource_path
        if not full_path.exists():
            raise FileNotFoundError(
                f"Resource not found: {resource_path}"
            )
        return full_path.read_bytes()

    # --- Internal methods ---

    def _build_injected_css(self) -> str:
        """Build the complete CSS to inject into the HTML.

        Combines font settings, view mode, dark mode, and highlight CSS.

        Returns:
            Combined CSS string.
        """
        css_parts: list[str] = []

        # Font settings
        css_parts.append(generate_font_css(self._font_settings))

        # View mode
        if self._view_mode == EPUBViewMode.PAGINATED:
            css_parts.append(
                generate_pagination_css(self._viewport_width, self._viewport_height)
            )
        else:
            css_parts.append(generate_scroll_css())

        # Dark mode
        if self._dark_mode:
            css_parts.append(generate_dark_mode_css())

        # Highlights
        if self._highlights:
            css_parts.append(generate_highlight_css(self._highlights))

        return "\n".join(css_parts)

    def _inject_css_into_html(self, html_content: str, css: str) -> str:
        """Inject CSS into HTML content.

        Inserts a <style> tag into the <head> section. If no <head> is found,
        prepends the style to the beginning of the content.

        Args:
            html_content: The original HTML content.
            css: CSS string to inject.

        Returns:
            HTML with injected CSS.
        """
        style_tag = f"<style type=\"text/css\">\n{css}\n</style>\n"

        # Try to inject into <head>
        head_match = re.search(r"(<head[^>]*>)", html_content, re.IGNORECASE)
        if head_match:
            insert_pos = head_match.end()
            return html_content[:insert_pos] + "\n" + style_tag + html_content[insert_pos:]

        # Try to inject before <body>
        body_match = re.search(r"(<body[^>]*>)", html_content, re.IGNORECASE)
        if body_match:
            return (
                html_content[: body_match.start()]
                + "<head>\n" + style_tag + "</head>\n"
                + html_content[body_match.start():]
            )

        # Fallback: prepend to content
        return style_tag + html_content


    def _extract_toc_from_html(self) -> list[TocEntry]:
        """Extract a table of contents from HTML heading elements.

        Scans the converted HTML for <h1>, <h2>, <h3> elements and
        builds a TOC structure from them.

        Returns:
            List of TocEntry objects representing the document structure.
        """
        if not self._html_content:
            return []

        entries: list[TocEntry] = []
        heading_pattern = re.compile(
            r"<h([1-3])[^>]*(?:id=[\"']([^\"']*)[\"'])?[^>]*>(.*?)</h\1>",
            re.IGNORECASE | re.DOTALL,
        )

        for match in heading_pattern.finditer(self._html_content):
            level = int(match.group(1))
            anchor_id = match.group(2) or ""
            title_raw = match.group(3)
            # Strip any HTML tags from the heading text
            title = re.sub(r"<[^>]+>", "", title_raw).strip()

            if title:
                href = f"#{anchor_id}" if anchor_id else ""
                entries.append(TocEntry(title=title, href=href))

        return entries

    @staticmethod
    def _strip_html_tags(html_content: str) -> str:
        """Extract plain text from HTML content by stripping all tags.

        Args:
            html_content: Raw HTML string.

        Returns:
            Plain text with HTML tags removed.
        """
        import html as html_module

        # Remove script and style elements
        text = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "",
            html_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Replace block elements with space
        text = re.sub(
            r"<(br|p|div|h[1-6]|li|tr|td|th|blockquote|pre)[^>]*/?>",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        # Remove remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = html_module.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
