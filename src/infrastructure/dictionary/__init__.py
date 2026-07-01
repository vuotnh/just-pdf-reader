"""Dictionary infrastructure: cache, local StarDict, and online API clients.

Implements the chain-of-responsibility lookup pattern:
  cache → StarDict → online API (configurable priority)
"""

from src.infrastructure.dictionary.dict_cache import DictCacheRepository
from src.infrastructure.dictionary.lookup_chain import DictionaryLookupChain, DictEntry
from src.infrastructure.dictionary.online_api import (
    OnlineDictionaryClient,
    OxfordClient,
    CambridgeClient,
    MerriamWebsterClient,
    WiktionaryClient,
)
from src.infrastructure.dictionary.stardict_reader import StarDictReader

__all__ = [
    "DictCacheRepository",
    "DictEntry",
    "DictionaryLookupChain",
    "OnlineDictionaryClient",
    "OxfordClient",
    "CambridgeClient",
    "MerriamWebsterClient",
    "WiktionaryClient",
    "StarDictReader",
]
