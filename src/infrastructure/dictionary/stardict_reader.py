"""Local StarDict format dictionary reader.

StarDict dictionaries consist of three files:
  - .ifo: metadata (bookname, wordcount, idxfilesize, sametypesequence)
  - .idx: sorted index mapping words to offsets/sizes in the .dict file
  - .dict (.dict.dz if compressed): the actual definitions

This module parses all three files and provides O(log n) word lookup via
binary search on the sorted index.
"""

from __future__ import annotations

import gzip
import logging
import struct
from dataclasses import dataclass
from pathlib import Path

from src.infrastructure.dictionary.lookup_chain import DictEntry, PartOfSpeech

logger = logging.getLogger(__name__)


@dataclass
class _IndexEntry:
    """An entry in the StarDict .idx file."""

    word: str
    offset: int
    size: int


class StarDictReader:
    """Reader for StarDict format dictionaries.

    Supports loading .ifo/.idx/.dict(.dz) dictionary files and looking up
    words with binary search on the sorted index.
    """

    def __init__(self, dict_dir: Path | str | None = None) -> None:
        """Initialize the StarDict reader.

        Args:
            dict_dir: Directory containing StarDict dictionary files (.ifo, .idx, .dict).
                     If None, the reader is created in an inactive state (lookup returns None).
        """
        self._dict_dir: Path | None = Path(dict_dir) if dict_dir else None
        self._index: list[_IndexEntry] = []
        self._dict_data: bytes = b""
        self._bookname: str = ""
        self._loaded: bool = False

        if self._dict_dir is not None:
            self._load()

    @property
    def source_name(self) -> str:
        """Identifier for this source in the lookup chain."""
        return "stardict"

    @property
    def is_loaded(self) -> bool:
        """Whether a dictionary has been successfully loaded."""
        return self._loaded

    @property
    def bookname(self) -> str:
        """Name of the loaded dictionary."""
        return self._bookname

    @property
    def word_count(self) -> int:
        """Number of words in the loaded index."""
        return len(self._index)

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in the StarDict dictionary.

        Uses binary search on the sorted index for O(log n) performance.

        Args:
            word: The word to look up (normalized/lowercased).
            language: Language code (used for context but not filtering in StarDict).

        Returns:
            DictEntry if found, None otherwise.
        """
        if not self._loaded:
            return None

        idx = self._binary_search(word)
        if idx is None:
            return None

        entry = self._index[idx]
        raw_definition = self._read_definition(entry.offset, entry.size)
        if raw_definition is None:
            return None

        return self._parse_definition(word, raw_definition, language)

    def _load(self) -> None:
        """Load the StarDict dictionary files from the configured directory."""
        if self._dict_dir is None:
            return

        try:
            ifo_files = list(self._dict_dir.glob("*.ifo"))
            if not ifo_files:
                logger.warning("No .ifo file found in %s", self._dict_dir)
                return

            ifo_path = ifo_files[0]
            base_name = ifo_path.stem

            self._parse_ifo(ifo_path)
            self._parse_idx(self._dict_dir / f"{base_name}.idx")
            self._load_dict_data(self._dict_dir, base_name)
            self._loaded = True
            logger.info(
                "Loaded StarDict dictionary '%s' with %d entries",
                self._bookname,
                len(self._index),
            )
        except Exception:
            logger.exception("Failed to load StarDict dictionary from %s", self._dict_dir)
            self._loaded = False

    def _parse_ifo(self, ifo_path: Path) -> None:
        """Parse the .ifo metadata file."""
        content = ifo_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("bookname="):
                self._bookname = line[len("bookname="):]

    def _parse_idx(self, idx_path: Path) -> None:
        """Parse the .idx binary index file.

        Format: null-terminated word string followed by 4-byte offset and 4-byte size,
        both in network byte order (big-endian).
        """
        if not idx_path.exists():
            logger.warning("Index file not found: %s", idx_path)
            return

        data = idx_path.read_bytes()
        pos = 0
        entries: list[_IndexEntry] = []

        while pos < len(data):
            # Find null terminator for word string
            null_pos = data.index(b"\x00", pos)
            word = data[pos:null_pos].decode("utf-8")
            pos = null_pos + 1

            # Read 4-byte offset and 4-byte size (big-endian unsigned)
            if pos + 8 > len(data):
                break
            offset, size = struct.unpack(">II", data[pos : pos + 8])
            pos += 8

            entries.append(_IndexEntry(word=word, offset=offset, size=size))

        self._index = entries

    def _load_dict_data(self, dict_dir: Path, base_name: str) -> None:
        """Load the .dict or .dict.dz definition data file."""
        dict_dz_path = dict_dir / f"{base_name}.dict.dz"
        dict_path = dict_dir / f"{base_name}.dict"

        if dict_dz_path.exists():
            with gzip.open(dict_dz_path, "rb") as f:
                self._dict_data = f.read()
        elif dict_path.exists():
            self._dict_data = dict_path.read_bytes()
        else:
            logger.warning("No .dict or .dict.dz file found in %s", dict_dir)

    def _binary_search(self, word: str) -> int | None:
        """Binary search for a word in the sorted index.

        Performs case-insensitive comparison.

        Returns:
            Index position if found, None otherwise.
        """
        low, high = 0, len(self._index) - 1
        word_lower = word.lower()

        while low <= high:
            mid = (low + high) // 2
            mid_word = self._index[mid].word.lower()

            if mid_word == word_lower:
                return mid
            elif mid_word < word_lower:
                low = mid + 1
            else:
                high = mid - 1

        return None

    def _read_definition(self, offset: int, size: int) -> str | None:
        """Read a definition from the .dict data at the given offset and size."""
        if offset + size > len(self._dict_data):
            return None
        raw = self._dict_data[offset : offset + size]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")

    def _parse_definition(self, word: str, raw: str, language: str) -> DictEntry:
        """Parse a raw definition string into a normalized DictEntry.

        StarDict definitions can vary in format. This parser handles common
        patterns: lines starting with part-of-speech labels, numbered definitions,
        and example sentences.

        Args:
            word: The looked-up word.
            raw: Raw definition text from the .dict file.
            language: Language code.

        Returns:
            Normalized DictEntry.
        """
        lines = [line.strip() for line in raw.split("\n") if line.strip()]

        ipa = ""
        parts_of_speech: list[PartOfSpeech] = []
        examples: list[str] = []
        synonyms: list[str] = []
        current_pos: PartOfSpeech | None = None

        pos_labels = {
            "n.", "v.", "adj.", "adv.", "prep.", "conj.", "pron.", "interj.",
            "noun", "verb", "adjective", "adverb", "preposition",
            "conjunction", "pronoun", "interjection",
        }

        for line in lines:
            # Check for IPA pronunciation
            if line.startswith("/") and line.endswith("/"):
                ipa = line
                continue

            # Check for IPA in brackets
            if line.startswith("[") and line.endswith("]"):
                ipa = line[1:-1]
                continue

            # Check for part of speech label
            lower_line = line.lower().rstrip(":")
            if lower_line in pos_labels or any(line.lower().startswith(p) for p in pos_labels):
                # Extract POS label
                pos_label = lower_line.split()[0].rstrip(".:")
                current_pos = PartOfSpeech(pos=pos_label, definitions=[])
                parts_of_speech.append(current_pos)
                # If there's text after the POS label, treat it as a definition
                remainder = line[len(pos_label):].strip().lstrip(".:")
                if remainder:
                    current_pos.definitions.append(remainder)
                continue

            # Check for synonym markers
            if line.lower().startswith("syn:") or line.lower().startswith("synonyms:"):
                syn_text = line.split(":", 1)[1].strip()
                synonyms.extend([s.strip() for s in syn_text.split(",") if s.strip()])
                continue

            # Check for example sentences (usually italicized or in quotes)
            if line.startswith('"') or line.startswith("'") or line.startswith("e.g."):
                examples.append(line.strip("\"'"))
                continue

            # Otherwise treat as a definition under current POS or generic
            if current_pos is not None:
                current_pos.definitions.append(line)
            else:
                # No POS context yet - create a generic one
                current_pos = PartOfSpeech(pos="", definitions=[line])
                parts_of_speech.append(current_pos)

        return DictEntry(
            word=word,
            ipa=ipa,
            parts_of_speech=parts_of_speech,
            examples=examples,
            synonyms=synonyms,
            source="stardict",
            language=language,
        )
