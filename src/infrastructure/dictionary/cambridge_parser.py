"""Cambridge Dictionary scraper and parser.

Fetches word definitions from dictionary.cambridge.org (English-Vietnamese
and English-English) and parses the HTML into structured dictionary data.

Uses stable semantic CSS classes as selectors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

_BASE_URL = "https://dictionary.cambridge.org"
_EN_VI_URL = f"{_BASE_URL}/dictionary/english-vietnamese/{{word}}"
_EN_EN_URL = f"{_BASE_URL}/dictionary/english/{{word}}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
}

_TIMEOUT = 8


@dataclass
class Pronunciation:
    ipa: str = ""
    audio_url: str = ""


@dataclass
class Sense:
    guideword: str = ""
    definition_en: str = ""
    definition_vi: str = ""
    examples: list[str] = field(default_factory=list)
    level: str = ""  # CEFR level: A1, A2, B1, B2, C1, C2


@dataclass
class Entry:
    pos: str = ""  # part of speech
    grammar: str = ""
    level: str = ""
    senses: list[Sense] = field(default_factory=list)


@dataclass
class CambridgeResult:
    word: str = ""
    uk_pronunciation: Pronunciation = field(default_factory=Pronunciation)
    us_pronunciation: Pronunciation = field(default_factory=Pronunciation)
    entries: list[Entry] = field(default_factory=list)
    idioms: list[str] = field(default_factory=list)
    phrasal_verbs: list[str] = field(default_factory=list)
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "word": self.word,
            "pronunciation": {
                "uk": {"ipa": self.uk_pronunciation.ipa, "audio": self.uk_pronunciation.audio_url},
                "us": {"ipa": self.us_pronunciation.ipa, "audio": self.us_pronunciation.audio_url},
            },
            "entries": [
                {
                    "pos": e.pos,
                    "grammar": e.grammar,
                    "level": e.level,
                    "senses": [
                        {
                            "guideword": s.guideword,
                            "definition_en": s.definition_en,
                            "definition_vi": s.definition_vi,
                            "examples": s.examples,
                            "level": s.level,
                        }
                        for s in e.senses
                    ],
                }
                for e in self.entries
            ],
            "idioms": self.idioms,
            "phrasal_verbs": self.phrasal_verbs,
            "source_url": self.source_url,
        }


def lookup_cambridge(word: str) -> CambridgeResult | None:
    """Look up a word from Cambridge Dictionary (EN-VI + EN-EN).

    Fetches both the English-Vietnamese and English-English pages,
    combining results for richer data.

    Args:
        word: The word to look up.

    Returns:
        CambridgeResult with parsed data, or None if not found.
    """
    word = word.strip().lower()
    if not word:
        return None

    logger.info("=== Cambridge Dictionary Lookup: '%s' ===", word)

    # Try English-Vietnamese first
    result = _fetch_and_parse(word, _EN_VI_URL.format(word=word))

    # If no entries found in EN-VI, try EN-EN
    if result is None or not result.entries:
        logger.info("EN-VI had no entries for '%s', trying EN-EN", word)
        en_result = _fetch_and_parse(word, _EN_EN_URL.format(word=word))
        if en_result and en_result.entries:
            if result is None:
                result = en_result
            else:
                # Merge: keep VI translations if available, add EN-only data
                result.entries = en_result.entries
                if not result.uk_pronunciation.ipa:
                    result.uk_pronunciation = en_result.uk_pronunciation
                if not result.us_pronunciation.ipa:
                    result.us_pronunciation = en_result.us_pronunciation

    if result:
        total_senses = sum(len(e.senses) for e in result.entries)
        logger.info("=== Lookup complete: '%s' → %d entries, %d senses ===",
                    word, len(result.entries), total_senses)
    else:
        logger.warning("=== Lookup failed: '%s' not found in any source ===", word)

    return result


def _fetch_and_parse(word: str, url: str) -> CambridgeResult | None:
    """Fetch a Cambridge Dictionary page and parse it.

    Args:
        word: The lookup word.
        url: Full URL to fetch.

    Returns:
        CambridgeResult or None if page not found / error.
    """
    logger.info("Cambridge lookup: fetching URL %s", url)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        logger.info("Cambridge response: status=%d, length=%d bytes, url=%s",
                    resp.status_code, len(resp.content), resp.url)
        if resp.status_code == 404:
            logger.warning("Cambridge 404: word '%s' not found at %s", word, url)
            return None
        resp.raise_for_status()
    except requests.ConnectionError as e:
        logger.error("Cambridge connection error for '%s': %s", word, e)
        return None
    except requests.Timeout as e:
        logger.error("Cambridge timeout for '%s' (limit=%ds): %s", word, _TIMEOUT, e)
        return None
    except requests.HTTPError as e:
        logger.error("Cambridge HTTP error for '%s': status=%d, %s",
                     word, e.response.status_code if e.response else 0, e)
        return None
    except requests.RequestException as e:
        logger.error("Cambridge request failed for '%s': %s", word, e)
        return None

    logger.debug("Cambridge parsing HTML for '%s' (%d chars)", word, len(resp.text))
    soup = BeautifulSoup(resp.text, "html.parser")
    result = _parse_page(soup, word, url)
    logger.info("Cambridge result for '%s': %d entries, uk_ipa='%s', us_ipa='%s'",
                word, len(result.entries),
                result.uk_pronunciation.ipa, result.us_pronunciation.ipa)
    return result


def _parse_page(soup: BeautifulSoup, word: str, url: str) -> CambridgeResult:
    """Parse a Cambridge Dictionary HTML page into structured data."""
    result = CambridgeResult(word=word, source_url=url)

    # 1. Headword
    hw_el = soup.select_one(".hw.dhw")
    if hw_el:
        result.word = hw_el.get_text(strip=True)

    # 2. Pronunciation
    result.uk_pronunciation = _parse_pronunciation(soup, "uk")
    result.us_pronunciation = _parse_pronunciation(soup, "us")

    # 3. Entries (pos-header blocks)
    # Cambridge groups entries by pos in .entry-body__el
    entry_blocks = soup.select(".entry-body__el")
    if not entry_blocks:
        # Fallback: try .pr.dictionary
        entry_blocks = soup.select(".pr.dictionary .pos-header")

    for block in entry_blocks:
        entry = _parse_entry_block(block)
        if entry.senses:
            result.entries.append(entry)

    # 4. Idioms
    for idiom_block in soup.select(".idiom-block"):
        title = idiom_block.select_one(".idiom-title")
        if title:
            result.idioms.append(title.get_text(strip=True))

    # 5. Phrasal verbs
    for pv_block in soup.select(".pv-block"):
        title = pv_block.select_one(".pv-title")
        if title:
            result.phrasal_verbs.append(title.get_text(strip=True))

    return result


def _parse_pronunciation(soup: BeautifulSoup, region: str) -> Pronunciation:
    """Parse UK or US pronunciation from the page.

    Args:
        soup: Parsed HTML.
        region: "uk" or "us".

    Returns:
        Pronunciation with IPA and audio URL.
    """
    pron = Pronunciation()

    # Find the pronunciation block for this region
    pron_block = soup.select_one(f".{region}.dpron-i")
    if not pron_block:
        return pron

    # IPA
    ipa_el = pron_block.select_one(".ipa.dipa")
    if not ipa_el:
        ipa_el = pron_block.select_one(".ipa")
    if ipa_el:
        pron.ipa = ipa_el.get_text(strip=True)

    # Audio URL
    audio_el = pron_block.select_one("source[type='audio/mpeg']")
    if audio_el and audio_el.get("src"):
        src = audio_el["src"]
        if src.startswith("/"):
            pron.audio_url = _BASE_URL + src
        else:
            pron.audio_url = src

    return pron


def _parse_entry_block(block: Tag) -> Entry:
    """Parse a single entry block (one part of speech)."""
    entry = Entry()

    # Part of speech
    pos_el = block.select_one(".pos.dpos")
    if pos_el:
        entry.pos = pos_el.get_text(strip=True)

    # Grammar info
    gram_el = block.select_one(".gram.dgram")
    if gram_el:
        entry.grammar = gram_el.get_text(strip=True)

    # CEFR level (entry-level)
    level_el = block.select_one(".epp-xref.dxref")
    if not level_el:
        level_el = block.select_one(".epp-xref")
    if level_el:
        entry.level = level_el.get_text(strip=True)

    # Senses
    sense_blocks = block.select(".sense-body.dsense_b")
    if not sense_blocks:
        # Try direct .def-block
        sense_blocks = block.select(".def-block.ddef_block")

    for sense_block in sense_blocks:
        sense = _parse_sense(sense_block)
        if sense.definition_en or sense.definition_vi:
            entry.senses.append(sense)

    return entry


def _parse_sense(sense_block: Tag) -> Sense:
    """Parse a single sense (meaning) block."""
    sense = Sense()

    # Guideword
    gw_el = sense_block.select_one(".guideword.dsense_gw span")
    if not gw_el:
        gw_el = sense_block.select_one(".guideword span")
    if gw_el:
        sense.guideword = gw_el.get_text(strip=True)

    # CEFR level for this sense
    level_el = sense_block.select_one(".epp-xref.dxref")
    if not level_el:
        level_el = sense_block.select_one(".epp-xref")
    if level_el:
        sense.level = level_el.get_text(strip=True)

    # English definition
    def_el = sense_block.select_one(".def.ddef_d")
    if def_el:
        sense.definition_en = def_el.get_text(" ", strip=True)
        # Remove trailing colon
        if sense.definition_en.endswith(":"):
            sense.definition_en = sense.definition_en[:-1].strip()

    # Vietnamese translation
    trans_el = sense_block.select_one(".trans.dtrans.dtrans-se")
    if not trans_el:
        trans_el = sense_block.select_one(".trans.dtrans")
    if trans_el:
        sense.definition_vi = trans_el.get_text(strip=True)

    # Examples
    for ex_el in sense_block.select(".eg.deg, .examp.dexamp"):
        ex_text = ex_el.get_text(" ", strip=True)
        if ex_text:
            sense.examples.append(ex_text)

    return sense
