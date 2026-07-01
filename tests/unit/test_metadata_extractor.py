"""Unit tests for the metadata extractor module.

Tests PDF and EPUB metadata extraction with mocked files,
fallback logic, and file hash computation.
"""

import base64
import hashlib
import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.parsers.metadata_extractor import (
    MetadataResult,
    _extract_epub_cover,
    _fallback_metadata,
    _find_opf_path,
    _parse_opf_metadata,
    compute_file_hash,
    extract_epub_metadata,
    extract_metadata,
    extract_pdf_metadata,
)


# ---------------------------------------------------------------------------
# File hash tests
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    """Tests for SHA-256 file hash computation."""

    def test_hash_of_known_content(self, tmp_path: Path):
        """Hash of known content matches expected SHA-256 digest."""
        content = b"hello world"
        file = tmp_path / "test.bin"
        file.write_bytes(content)

        result = compute_file_hash(file)
        expected = hashlib.sha256(content).hexdigest()
        assert result == expected

    def test_hash_of_empty_file(self, tmp_path: Path):
        """Hash of empty file is the SHA-256 of empty bytes."""
        file = tmp_path / "empty.bin"
        file.write_bytes(b"")

        result = compute_file_hash(file)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_different_content_produces_different_hashes(self, tmp_path: Path):
        """Different file contents produce different hashes."""
        file1 = tmp_path / "a.bin"
        file1.write_bytes(b"content A")

        file2 = tmp_path / "b.bin"
        file2.write_bytes(b"content B")

        assert compute_file_hash(file1) != compute_file_hash(file2)

    def test_same_content_produces_same_hash(self, tmp_path: Path):
        """Identical content in different files produces the same hash."""
        content = b"identical content"
        file1 = tmp_path / "copy1.bin"
        file1.write_bytes(content)

        file2 = tmp_path / "copy2.bin"
        file2.write_bytes(content)

        assert compute_file_hash(file1) == compute_file_hash(file2)


# ---------------------------------------------------------------------------
# Fallback metadata tests
# ---------------------------------------------------------------------------


class TestFallbackMetadata:
    """Tests for fallback logic when extraction fails."""

    def test_fallback_uses_filename_stem(self, tmp_path: Path):
        """Fallback title is the filename without extension."""
        file = tmp_path / "My Great Book.pdf"
        file.write_bytes(b"not a real pdf")

        result = _fallback_metadata(file)
        assert result.title == "My Great Book"
        assert result.author is None
        assert result.publisher is None
        assert result.language is None
        assert result.page_count is None
        assert result.cover_image is None

    def test_fallback_computes_hash(self, tmp_path: Path):
        """Fallback still computes file hash when possible."""
        content = b"some bytes"
        file = tmp_path / "test.epub"
        file.write_bytes(content)

        result = _fallback_metadata(file)
        expected_hash = hashlib.sha256(content).hexdigest()
        assert result.file_hash == expected_hash


# ---------------------------------------------------------------------------
# PDF metadata extraction tests
# ---------------------------------------------------------------------------


class TestPdfMetadataExtraction:
    """Tests for PDF metadata extraction via PyMuPDF."""

    def test_extract_metadata_from_valid_pdf(self, tmp_path: Path):
        """Extracts title, author, page count from a valid PDF."""
        # Create a minimal PDF with PyMuPDF
        import fitz

        doc = fitz.open()
        doc.set_metadata({"title": "Test PDF", "author": "Jane Doe", "producer": "TestPublisher"})
        page = doc.new_page()
        doc.save(str(tmp_path / "test.pdf"))
        doc.close()

        result = extract_pdf_metadata(tmp_path / "test.pdf")
        assert result.title == "Test PDF"
        assert result.author == "Jane Doe"
        assert result.publisher == "TestPublisher"
        assert result.page_count == 1
        assert result.file_hash != ""

    def test_extract_cover_image_from_pdf(self, tmp_path: Path):
        """Cover image is extracted as Base64-encoded PNG from first page."""
        import fitz

        doc = fitz.open()
        page = doc.new_page(width=200, height=300)
        # Draw something so the cover isn't blank
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(10, 10, 190, 290))
        shape.finish(color=(1, 0, 0))
        shape.commit()
        doc.save(str(tmp_path / "cover.pdf"))
        doc.close()

        result = extract_pdf_metadata(tmp_path / "cover.pdf")
        assert result.cover_image is not None
        # Verify it's valid Base64 that decodes to PNG
        decoded = base64.b64decode(result.cover_image)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes

    def test_fallback_when_metadata_empty(self, tmp_path: Path):
        """Uses filename as title when PDF metadata fields are empty."""
        import fitz

        doc = fitz.open()
        doc.new_page()
        # Don't set any metadata
        doc.save(str(tmp_path / "My Document.pdf"))
        doc.close()

        result = extract_pdf_metadata(tmp_path / "My Document.pdf")
        assert result.title == "My Document"

    def test_fallback_on_corrupt_file(self, tmp_path: Path):
        """Returns fallback metadata when file is not a valid PDF."""
        file = tmp_path / "corrupt.pdf"
        file.write_bytes(b"this is not a pdf")

        result = extract_pdf_metadata(file)
        assert result.title == "corrupt"


# ---------------------------------------------------------------------------
# EPUB metadata extraction tests
# ---------------------------------------------------------------------------


def _create_epub(
    tmp_path: Path,
    filename: str = "test.epub",
    title: str | None = "Test EPUB",
    author: str | None = "John Smith",
    publisher: str | None = "EPUB Press",
    language: str | None = "en",
    include_cover: bool = False,
    cover_properties: bool = True,
) -> Path:
    """Helper to create a minimal valid EPUB file for testing."""
    epub_path = tmp_path / filename

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    # Build Dublin Core metadata entries
    dc_entries = ""
    if title:
        dc_entries += f"    <dc:title>{title}</dc:title>\n"
    if author:
        dc_entries += f"    <dc:creator>{author}</dc:creator>\n"
    if publisher:
        dc_entries += f"    <dc:publisher>{publisher}</dc:publisher>\n"
    if language:
        dc_entries += f"    <dc:language>{language}</dc:language>\n"

    # Build manifest items
    manifest_items = '    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>\n'
    if include_cover:
        if cover_properties:
            manifest_items += '    <item id="cover-img" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>\n'
        else:
            manifest_items += '    <item id="cover-img" href="images/cover.jpg" media-type="image/jpeg"/>\n'

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
{dc_entries}  </metadata>
  <manifest>
{manifest_items}  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>"""

    chapter_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1</title></head>
<body><p>Hello world.</p></body>
</html>"""

    with zipfile.ZipFile(str(epub_path), "w") as zf:
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)
        if include_cover:
            # Write a small JPEG-like placeholder (just recognizable bytes for testing)
            fake_cover = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG SOI marker + padding
            zf.writestr("OEBPS/images/cover.jpg", fake_cover)

    return epub_path


class TestEpubMetadataExtraction:
    """Tests for EPUB metadata extraction via OPF parsing."""

    def test_extract_full_metadata(self, tmp_path: Path):
        """Extracts title, author, publisher, language from a valid EPUB."""
        epub_path = _create_epub(tmp_path)

        result = extract_epub_metadata(epub_path)
        assert result.title == "Test EPUB"
        assert result.author == "John Smith"
        assert result.publisher == "EPUB Press"
        assert result.language == "en"
        assert result.page_count is None  # EPUB doesn't have fixed pages
        assert result.file_hash != ""

    def test_extract_cover_image(self, tmp_path: Path):
        """Cover image is extracted from manifest cover-image property."""
        epub_path = _create_epub(tmp_path, include_cover=True)

        result = extract_epub_metadata(epub_path)
        assert result.cover_image is not None
        decoded = base64.b64decode(result.cover_image)
        # Verify it starts with JPEG marker
        assert decoded[:2] == b"\xff\xd8"

    def test_no_cover_when_absent(self, tmp_path: Path):
        """Cover image is None when no cover is in the manifest."""
        epub_path = _create_epub(tmp_path, include_cover=False)

        result = extract_epub_metadata(epub_path)
        assert result.cover_image is None

    def test_fallback_when_no_title(self, tmp_path: Path):
        """Uses filename stem as title when title metadata is empty."""
        epub_path = _create_epub(tmp_path, filename="My Novel.epub", title=None)

        result = extract_epub_metadata(epub_path)
        assert result.title == "My Novel"

    def test_fallback_on_corrupt_epub(self, tmp_path: Path):
        """Returns fallback metadata for a corrupt/invalid EPUB file."""
        file = tmp_path / "corrupt.epub"
        file.write_bytes(b"not a zip file at all")

        result = extract_epub_metadata(file)
        assert result.title == "corrupt"
        assert result.author is None

    def test_missing_container_xml(self, tmp_path: Path):
        """Falls back when container.xml is missing."""
        epub_path = tmp_path / "no_container.epub"
        with zipfile.ZipFile(str(epub_path), "w") as zf:
            zf.writestr("OEBPS/content.opf", "<package/>")

        result = extract_epub_metadata(epub_path)
        assert result.title == "no_container"


# ---------------------------------------------------------------------------
# Dispatch function tests
# ---------------------------------------------------------------------------


class TestExtractMetadata:
    """Tests for the main extract_metadata dispatch function."""

    def test_dispatches_to_pdf_extractor(self, tmp_path: Path):
        """PDF files are routed to the PDF extractor."""
        import fitz

        doc = fitz.open()
        doc.set_metadata({"title": "PDF Title"})
        doc.new_page()
        doc.save(str(tmp_path / "book.pdf"))
        doc.close()

        result = extract_metadata(tmp_path / "book.pdf")
        assert result.title == "PDF Title"

    def test_dispatches_to_epub_extractor(self, tmp_path: Path):
        """EPUB files are routed to the EPUB extractor."""
        epub_path = _create_epub(tmp_path, title="EPUB Title")

        result = extract_metadata(epub_path)
        assert result.title == "EPUB Title"

    def test_unsupported_format_uses_fallback(self, tmp_path: Path):
        """Unsupported formats get fallback metadata."""
        file = tmp_path / "document.txt"
        file.write_bytes(b"plain text")

        result = extract_metadata(file)
        assert result.title == "document"

    def test_case_insensitive_extension(self, tmp_path: Path):
        """Extension matching is case-insensitive."""
        epub_path = _create_epub(tmp_path, filename="BOOK.EPUB", title="Upper Case")
        # Rename the file with uppercase extension
        # The helper already created it as BOOK.EPUB

        result = extract_metadata(epub_path)
        assert result.title == "Upper Case"


# ---------------------------------------------------------------------------
# OPF parsing helper tests
# ---------------------------------------------------------------------------


class TestOPFParsing:
    """Tests for OPF XML parsing helpers."""

    def test_parse_opf_metadata_extracts_all_fields(self):
        """All Dublin Core fields are extracted from well-formed OPF."""
        opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Parsing Test</dc:title>
    <dc:creator>Author Name</dc:creator>
    <dc:publisher>Publisher Inc</dc:publisher>
    <dc:language>fr</dc:language>
  </metadata>
</package>"""

        result = _parse_opf_metadata(opf)
        assert result["title"] == "Parsing Test"
        assert result["author"] == "Author Name"
        assert result["publisher"] == "Publisher Inc"
        assert result["language"] == "fr"

    def test_parse_opf_metadata_handles_missing_fields(self):
        """Missing metadata fields return None."""
        opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Only Title</dc:title>
  </metadata>
</package>"""

        result = _parse_opf_metadata(opf)
        assert result["title"] == "Only Title"
        assert result["author"] is None
        assert result["publisher"] is None
        assert result["language"] is None

    def test_parse_opf_metadata_handles_invalid_xml(self):
        """Invalid XML returns all None values without raising."""
        result = _parse_opf_metadata("not xml at all <<<")
        assert result["title"] is None
        assert result["author"] is None
