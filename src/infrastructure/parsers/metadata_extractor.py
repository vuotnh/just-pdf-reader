"""Metadata extraction for PDF and EPUB files.

Provides format-specific extractors for:
- PDF: metadata via PyMuPDF (fitz), first-page cover thumbnail
- EPUB: metadata via OPF parsing (zipfile + xml.etree), cover image from manifest

Fallback logic: when metadata extraction fails, uses the filename stem as title.
File hash computation (SHA-256) supports deduplication.
"""

from __future__ import annotations

import base64
import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz  # PyMuPDF


@dataclass
class MetadataResult:
    """Structured result of metadata extraction from an ebook file."""

    title: str
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    page_count: int | None = None
    cover_image: str | None = None  # Base64-encoded image data
    file_hash: str = ""


def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Compute SHA-256 hash of a file for deduplication.

    Reads the file in 64KB chunks to handle large files efficiently.
    """
    h = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf_metadata(file_path: Path) -> MetadataResult:
    """Extract metadata from a PDF file using PyMuPDF.

    Extracts title, author, page count from doc.metadata.
    Renders the first page as a thumbnail for the cover image.
    Falls back to filename stem as title if metadata is missing.
    """
    try:
        doc = fitz.open(str(file_path))
    except Exception:
        return _fallback_metadata(file_path)

    try:
        meta = doc.metadata or {}
        title = meta.get("title", "").strip() or None
        author = meta.get("author", "").strip() or None
        publisher = meta.get("producer", "").strip() or None
        language = None  # PDF metadata rarely includes language reliably
        page_count = doc.page_count

        # Extract cover image: render first page as thumbnail
        cover_image = _extract_pdf_cover(doc)

        file_hash = compute_file_hash(file_path)

        result = MetadataResult(
            title=title if title else file_path.stem,
            author=author,
            publisher=publisher,
            language=language,
            page_count=page_count,
            cover_image=cover_image,
            file_hash=file_hash,
        )
        return result
    finally:
        doc.close()


def _extract_pdf_cover(doc: fitz.Document) -> str | None:
    """Render PDF first page as a thumbnail (150px wide) and return Base64-encoded PNG."""
    if doc.page_count == 0:
        return None

    try:
        page = doc[0]
        # Scale to approximately 150px wide thumbnail
        zoom = 150.0 / page.rect.width if page.rect.width > 0 else 1.0
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        png_bytes = pixmap.tobytes("png")
        return base64.b64encode(png_bytes).decode("ascii")
    except Exception:
        return None


def extract_epub_metadata(file_path: Path) -> MetadataResult:
    """Extract metadata from an EPUB file by parsing the OPF (content.opf).

    Parses the container.xml to locate the OPF file, then extracts
    Dublin Core metadata (title, creator, publisher, language).
    Extracts cover image from the manifest if present.
    Falls back to filename stem as title if parsing fails.
    """
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            opf_path = _find_opf_path(zf)
            if opf_path is None:
                return _fallback_metadata(file_path)

            opf_content = zf.read(opf_path).decode("utf-8")
            metadata = _parse_opf_metadata(opf_content)
            cover_image = _extract_epub_cover(zf, opf_content, opf_path)

            file_hash = compute_file_hash(file_path)

            return MetadataResult(
                title=metadata.get("title") or file_path.stem,
                author=metadata.get("author"),
                publisher=metadata.get("publisher"),
                language=metadata.get("language"),
                page_count=None,  # EPUB doesn't have fixed page count
                cover_image=cover_image,
                file_hash=file_hash,
            )
    except Exception:
        return _fallback_metadata(file_path)


def _find_opf_path(zf: zipfile.ZipFile) -> str | None:
    """Locate the OPF file path from META-INF/container.xml."""
    try:
        container_xml = zf.read("META-INF/container.xml").decode("utf-8")
        root = ET.fromstring(container_xml)

        # Namespace for container.xml
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = root.find(".//c:rootfile", ns)
        if rootfile is not None:
            return rootfile.get("full-path")

        # Try without namespace (some EPUBs omit it)
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is not None:
            return rootfile.get("full-path")

        return None
    except Exception:
        return None


def _parse_opf_metadata(opf_content: str) -> dict[str, str | None]:
    """Parse Dublin Core metadata from OPF XML content."""
    result: dict[str, str | None] = {
        "title": None,
        "author": None,
        "publisher": None,
        "language": None,
    }

    try:
        root = ET.fromstring(opf_content)

        # Dublin Core namespace
        dc_ns = "http://purl.org/dc/elements/1.1/"
        opf_ns = "http://www.idpf.org/2007/opf"

        # Search in metadata element
        metadata_el = root.find(f".//{{{opf_ns}}}metadata")
        if metadata_el is None:
            # Try without OPF namespace wrapping
            metadata_el = root

        title_el = metadata_el.find(f".//{{{dc_ns}}}title")
        if title_el is not None and title_el.text:
            result["title"] = title_el.text.strip()

        creator_el = metadata_el.find(f".//{{{dc_ns}}}creator")
        if creator_el is not None and creator_el.text:
            result["author"] = creator_el.text.strip()

        publisher_el = metadata_el.find(f".//{{{dc_ns}}}publisher")
        if publisher_el is not None and publisher_el.text:
            result["publisher"] = publisher_el.text.strip()

        language_el = metadata_el.find(f".//{{{dc_ns}}}language")
        if language_el is not None and language_el.text:
            result["language"] = language_el.text.strip()

    except Exception:
        pass

    return result


def _extract_epub_cover(
    zf: zipfile.ZipFile, opf_content: str, opf_path: str
) -> str | None:
    """Extract cover image from EPUB manifest.

    Looks for an item with properties="cover-image" or id containing "cover".
    """
    try:
        root = ET.fromstring(opf_content)
        opf_ns = "http://www.idpf.org/2007/opf"

        manifest = root.find(f".//{{{opf_ns}}}manifest")
        if manifest is None:
            return None

        # Determine base directory of the OPF file for resolving relative paths
        opf_dir = str(Path(opf_path).parent)
        if opf_dir == ".":
            opf_dir = ""

        # Strategy 1: Look for item with properties="cover-image"
        for item in manifest.findall(f"{{{opf_ns}}}item"):
            props = item.get("properties", "")
            if "cover-image" in props:
                href = item.get("href", "")
                return _read_cover_from_zip(zf, href, opf_dir)

        # Strategy 2: Look for meta element with name="cover" pointing to manifest item
        metadata_el = root.find(f".//{{{opf_ns}}}metadata")
        if metadata_el is not None:
            for meta in metadata_el.findall(f"{{{opf_ns}}}meta"):
                if meta.get("name") == "cover":
                    cover_id = meta.get("content", "")
                    # Find the manifest item with this id
                    for item in manifest.findall(f"{{{opf_ns}}}item"):
                        if item.get("id") == cover_id:
                            href = item.get("href", "")
                            return _read_cover_from_zip(zf, href, opf_dir)

        # Strategy 3: Look for manifest item with id containing "cover" and image media type
        for item in manifest.findall(f"{{{opf_ns}}}item"):
            item_id = (item.get("id") or "").lower()
            media_type = (item.get("media-type") or "").lower()
            if "cover" in item_id and media_type.startswith("image/"):
                href = item.get("href", "")
                return _read_cover_from_zip(zf, href, opf_dir)

        return None
    except Exception:
        return None


def _read_cover_from_zip(
    zf: zipfile.ZipFile, href: str, opf_dir: str
) -> str | None:
    """Read a cover image file from the EPUB zip archive and return Base64-encoded data."""
    try:
        # Resolve relative path against OPF directory
        if opf_dir:
            full_path = f"{opf_dir}/{href}"
        else:
            full_path = href

        # Normalize path separators
        full_path = full_path.replace("\\", "/")

        image_data = zf.read(full_path)
        return base64.b64encode(image_data).decode("ascii")
    except (KeyError, Exception):
        return None


def _fallback_metadata(file_path: Path) -> MetadataResult:
    """Create a metadata result using the filename stem as title.

    Used when metadata extraction fails completely.
    """
    file_hash = ""
    try:
        file_hash = compute_file_hash(file_path)
    except Exception:
        pass

    return MetadataResult(
        title=file_path.stem,
        file_hash=file_hash,
    )


def extract_metadata(file_path: Path) -> MetadataResult:
    """Extract metadata from a file based on its extension.

    Dispatches to the appropriate format-specific extractor:
    - .pdf -> extract_pdf_metadata
    - .epub -> extract_epub_metadata

    For unsupported formats, returns fallback metadata using the filename.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf_metadata(file_path)
    elif suffix == ".epub":
        return extract_epub_metadata(file_path)
    else:
        return _fallback_metadata(file_path)
