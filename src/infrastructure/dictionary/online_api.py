"""Online dictionary API clients.

Provides clients for Oxford, Cambridge, Merriam Webster, and Wiktionary APIs.
Each client implements the DictionarySource protocol and returns normalized
DictEntry results.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from src.infrastructure.dictionary.lookup_chain import DictEntry, PartOfSpeech

logger = logging.getLogger(__name__)


class OnlineDictionaryClient(ABC):
    """Base class for online dictionary API clients.

    Subclasses implement source-specific parsing while sharing common
    HTTP request infrastructure.
    """

    def __init__(self, api_key: str = "", timeout: float = 5.0) -> None:
        """Initialize the online client.

        Args:
            api_key: API key for authenticated endpoints (not needed for all sources).
            timeout: HTTP request timeout in seconds.
        """
        self._api_key = api_key
        self._timeout = timeout

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source."""
        ...

    @abstractmethod
    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word using this online source.

        Args:
            word: The word to look up.
            language: Language code.

        Returns:
            DictEntry if found, None otherwise.
        """
        ...

    def _http_get(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        """Make an HTTP GET request and return parsed JSON response.

        Args:
            url: The URL to request.
            headers: Optional HTTP headers.

        Returns:
            Parsed JSON dict, or None on error.
        """
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug("Word not found at %s", url)
            else:
                logger.warning("HTTP %d from %s", e.code, url)
            return None
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
            logger.warning("Request failed for %s: %s", url, e)
            return None


class OxfordClient(OnlineDictionaryClient):
    """Client for the Oxford Dictionaries API.

    Requires an API key (app_id + app_key) for access.
    See: https://developer.oxforddictionaries.com/
    """

    BASE_URL = "https://od-api-sandbox.oxforddictionaries.com/api/v2"

    def __init__(self, app_id: str = "", app_key: str = "", timeout: float = 5.0) -> None:
        super().__init__(api_key=app_key, timeout=timeout)
        self._app_id = app_id
        self._app_key = app_key

    @property
    def source_name(self) -> str:
        return "oxford"

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in the Oxford Dictionary API."""
        lang_code = "en-us" if language == "en" else language
        url = f"{self.BASE_URL}/entries/{lang_code}/{word}"
        headers = {
            "app_id": self._app_id,
            "app_key": self._app_key,
        }
        data = self._http_get(url, headers)
        if data is None:
            return None

        return self._parse_response(word, data, language)

    def _parse_response(self, word: str, data: dict[str, Any], language: str) -> DictEntry | None:
        """Parse Oxford API response into DictEntry."""
        try:
            results = data.get("results", [])
            if not results:
                return None

            ipa = ""
            parts_of_speech: list[PartOfSpeech] = []
            examples: list[str] = []
            synonyms: list[str] = []

            for result in results:
                for lexical_entry in result.get("lexicalEntries", []):
                    pos = lexical_entry.get("lexicalCategory", {}).get("text", "")

                    for entry in lexical_entry.get("entries", []):
                        # Get pronunciation
                        for pron in entry.get("pronunciations", []):
                            if pron.get("phoneticNotation") == "IPA" and not ipa:
                                ipa = f"/{pron.get('phoneticSpelling', '')}/"

                        definitions: list[str] = []
                        for sense in entry.get("senses", []):
                            for defn in sense.get("definitions", []):
                                definitions.append(defn)
                            for ex in sense.get("examples", []):
                                examples.append(ex.get("text", ""))
                            for syn in sense.get("synonyms", []):
                                synonyms.append(syn.get("text", ""))

                        if definitions:
                            parts_of_speech.append(PartOfSpeech(pos=pos, definitions=definitions))

            if not parts_of_speech:
                return None

            return DictEntry(
                word=word,
                ipa=ipa,
                parts_of_speech=parts_of_speech,
                examples=examples,
                synonyms=synonyms,
                source="oxford",
                language=language,
            )
        except (KeyError, IndexError, TypeError):
            logger.exception("Failed to parse Oxford response for '%s'", word)
            return None


class CambridgeClient(OnlineDictionaryClient):
    """Client for the Cambridge Dictionary API.

    Note: Cambridge doesn't have a public API, so this client scrapes
    the free dictionary page structure. For production use, consider
    their licensed API access.
    """

    BASE_URL = "https://dictionary.cambridge.org/api/v1"

    def __init__(self, api_key: str = "", timeout: float = 5.0) -> None:
        super().__init__(api_key=api_key, timeout=timeout)

    @property
    def source_name(self) -> str:
        return "cambridge"

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in the Cambridge Dictionary.

        Note: This is a placeholder implementation. Cambridge requires
        licensed API access for programmatic lookups.
        """
        url = f"{self.BASE_URL}/dictionaries/english/entries/{word}"
        headers = {}
        if self._api_key:
            headers["accessKey"] = self._api_key

        data = self._http_get(url, headers)
        if data is None:
            return None

        return self._parse_response(word, data, language)

    def _parse_response(self, word: str, data: dict[str, Any], language: str) -> DictEntry | None:
        """Parse Cambridge API response into DictEntry."""
        try:
            entry_list = data.get("entryContent", {}).get("entries", [])
            if not entry_list:
                return None

            ipa = ""
            parts_of_speech: list[PartOfSpeech] = []
            examples: list[str] = []
            synonyms: list[str] = []

            for entry in entry_list:
                pos = entry.get("partOfSpeech", "")

                # Pronunciation
                for pron in entry.get("pronunciations", []):
                    if pron.get("ipa") and not ipa:
                        ipa = f"/{pron['ipa']}/"

                definitions: list[str] = []
                for sense in entry.get("senses", []):
                    for defn in sense.get("definitions", []):
                        definitions.append(defn)
                    for ex in sense.get("examples", []):
                        examples.append(ex.get("text", ""))

                if definitions:
                    parts_of_speech.append(PartOfSpeech(pos=pos, definitions=definitions))

            if not parts_of_speech:
                return None

            return DictEntry(
                word=word,
                ipa=ipa,
                parts_of_speech=parts_of_speech,
                examples=examples,
                synonyms=synonyms,
                source="cambridge",
                language=language,
            )
        except (KeyError, IndexError, TypeError):
            logger.exception("Failed to parse Cambridge response for '%s'", word)
            return None


class MerriamWebsterClient(OnlineDictionaryClient):
    """Client for the Merriam-Webster Dictionary API.

    Requires an API key from: https://dictionaryapi.com/
    """

    BASE_URL = "https://dictionaryapi.com/api/v3/references/collegiate/json"

    def __init__(self, api_key: str = "", timeout: float = 5.0) -> None:
        super().__init__(api_key=api_key, timeout=timeout)

    @property
    def source_name(self) -> str:
        return "merriam_webster"

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in Merriam-Webster."""
        if not self._api_key:
            logger.debug("Merriam-Webster API key not configured")
            return None

        url = f"{self.BASE_URL}/{word}?key={self._api_key}"
        data = self._http_get(url)
        if data is None:
            return None

        # MW returns a list; if it's a list of strings, those are suggestions
        if isinstance(data, list) and data and isinstance(data[0], str):
            logger.debug("Word '%s' not found; suggestions: %s", word, data[:5])
            return None

        return self._parse_response(word, data, language)

    def _parse_response(
        self, word: str, data: Any, language: str
    ) -> DictEntry | None:
        """Parse Merriam-Webster API response into DictEntry."""
        try:
            if not isinstance(data, list) or not data:
                return None

            ipa = ""
            parts_of_speech: list[PartOfSpeech] = []
            examples: list[str] = []
            synonyms: list[str] = []

            for entry in data:
                if not isinstance(entry, dict):
                    continue

                pos = entry.get("fl", "")

                # Pronunciation
                if not ipa:
                    hwi = entry.get("hwi", {})
                    for prs in hwi.get("prs", []):
                        if prs.get("ipa"):
                            ipa = f"/{prs['ipa']}/"
                            break
                        elif prs.get("mw"):
                            ipa = prs["mw"]
                            break

                # Definitions
                definitions: list[str] = []
                for def_section in entry.get("def", []):
                    for sense_seq in def_section.get("sseq", []):
                        for sense_group in sense_seq:
                            if isinstance(sense_group, list) and len(sense_group) >= 2:
                                sense_data = sense_group[1]
                                if isinstance(sense_data, dict):
                                    dt = sense_data.get("dt", [])
                                    for dt_item in dt:
                                        if isinstance(dt_item, list) and dt_item[0] == "text":
                                            # Strip MW markup
                                            text = dt_item[1]
                                            text = text.replace("{bc}", "")
                                            text = text.replace("{/it}", "")
                                            text = text.replace("{it}", "")
                                            definitions.append(text.strip())
                                        elif isinstance(dt_item, list) and dt_item[0] == "vis":
                                            for vis in dt_item[1]:
                                                ex_text = vis.get("t", "")
                                                ex_text = ex_text.replace("{it}", "")
                                                ex_text = ex_text.replace("{/it}", "")
                                                examples.append(ex_text.strip())

                # Synonyms
                for syn_list in entry.get("syns", []):
                    for pt in syn_list.get("pt", []):
                        if isinstance(pt, list) and pt[0] == "text":
                            syn_text = pt[1].replace("{sc}", "").replace("{/sc}", "")
                            synonyms.extend([s.strip() for s in syn_text.split(",") if s.strip()])

                if definitions:
                    parts_of_speech.append(PartOfSpeech(pos=pos, definitions=definitions))

            if not parts_of_speech:
                return None

            return DictEntry(
                word=word,
                ipa=ipa,
                parts_of_speech=parts_of_speech,
                examples=examples,
                synonyms=synonyms,
                source="merriam_webster",
                language=language,
            )
        except (KeyError, IndexError, TypeError):
            logger.exception("Failed to parse Merriam-Webster response for '%s'", word)
            return None


class WiktionaryClient(OnlineDictionaryClient):
    """Client for Wiktionary (free, no API key required).

    Uses the Wiktionary REST API to fetch word definitions.
    See: https://en.wiktionary.org/api/rest_v1/
    """

    BASE_URL = "https://en.wiktionary.org/api/rest_v1/page/definition"

    def __init__(self, timeout: float = 5.0) -> None:
        super().__init__(api_key="", timeout=timeout)

    @property
    def source_name(self) -> str:
        return "wiktionary"

    def lookup(self, word: str, language: str = "en") -> DictEntry | None:
        """Look up a word in Wiktionary."""
        url = f"{self.BASE_URL}/{word}"
        headers = {
            "User-Agent": "AIEbookReader/0.1 (dictionary lookup)",
            "Accept": "application/json",
        }
        data = self._http_get(url, headers)
        if data is None:
            return None

        return self._parse_response(word, data, language)

    def _parse_response(self, word: str, data: dict[str, Any], language: str) -> DictEntry | None:
        """Parse Wiktionary REST API response into DictEntry."""
        try:
            # Wiktionary groups entries by language
            lang_key = "en"  # default to English
            if language == "en":
                lang_key = "en"
            entries = data.get(lang_key, [])
            if not entries:
                # Try any available language
                for key, value in data.items():
                    if isinstance(value, list) and value:
                        entries = value
                        break

            if not entries:
                return None

            ipa = ""
            parts_of_speech: list[PartOfSpeech] = []
            examples: list[str] = []
            synonyms: list[str] = []

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                pos = entry.get("partOfSpeech", "")
                definitions: list[str] = []

                for defn in entry.get("definitions", []):
                    if not isinstance(defn, dict):
                        continue
                    definition_text = defn.get("definition", "")
                    if definition_text:
                        # Strip HTML tags from Wiktionary definitions
                        import re

                        clean = re.sub(r"<[^>]+>", "", definition_text)
                        definitions.append(clean)

                    # Examples from Wiktionary
                    for ex in defn.get("examples", []):
                        if isinstance(ex, str):
                            examples.append(re.sub(r"<[^>]+>", "", ex))

                if definitions:
                    parts_of_speech.append(PartOfSpeech(pos=pos, definitions=definitions))

            if not parts_of_speech:
                return None

            return DictEntry(
                word=word,
                ipa=ipa,
                parts_of_speech=parts_of_speech,
                examples=examples,
                synonyms=synonyms,
                source="wiktionary",
                language=language,
            )
        except (KeyError, IndexError, TypeError):
            logger.exception("Failed to parse Wiktionary response for '%s'", word)
            return None
