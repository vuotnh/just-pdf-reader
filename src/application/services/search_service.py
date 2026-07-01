"""Search service implementing the ISearchService protocol using SQLite FTS5.

Provides unified full-text search across books, annotations, and vocabulary
entries. Supports search operators (exact phrase, AND, OR, exclude),
result ranking by relevance, and grouping by category.

Requirements: 10.1–10.6
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import Engine, text


# ---------------------------------------------------------------------------
# Search result data structures
# ---------------------------------------------------------------------------


class SearchCategory(Enum):
    """Categories for grouping search results."""

    BOOKS = "Books"
    ANNOTATIONS = "Annotations"
    VOCABULARY = "Vocabulary"
    NOTES = "Notes"


@dataclass
class SearchResultItem:
    """A single search result entry.

    Attributes:
        entity_id: The ID of the matched entity (book, annotation, or vocabulary entry).
        category: The category this result belongs to.
        title: Display title for the result.
        snippet: Text snippet with the matched content.
        rank: FTS5 relevance rank (lower is more relevant).
        book_id: The associated book ID for navigation (if applicable).
        position_data: Position data for navigating to the exact location.
    """

    entity_id: str
    category: SearchCategory
    title: str
    snippet: str
    rank: float = 0.0
    book_id: str | None = None
    position_data: str | None = None


@dataclass
class SearchResults:
    """Container for grouped search results.

    Attributes:
        query: The original search query.
        items: All result items sorted by relevance.
        total_count: Total number of results across all categories.
    """

    query: str
    items: list[SearchResultItem] = field(default_factory=list)
    total_count: int = 0

    def by_category(self, category: SearchCategory) -> list[SearchResultItem]:
        """Return results filtered to a specific category."""
        return [item for item in self.items if item.category == category]

    @property
    def grouped(self) -> dict[SearchCategory, list[SearchResultItem]]:
        """Return results grouped by category."""
        groups: dict[SearchCategory, list[SearchResultItem]] = {}
        for item in self.items:
            groups.setdefault(item.category, []).append(item)
        return groups


# ---------------------------------------------------------------------------
# SearchService implementation
# ---------------------------------------------------------------------------


class SearchService:
    """Application-layer service for full-text search using SQLite FTS5.

    Implements the ISearchService protocol from the design document:
    - Unified search across books_fts, annotations_fts, vocabulary_fts
    - Search operators: exact phrase (quotes), AND, OR, exclude (minus)
    - Result ranking by FTS5 relevance score
    - Grouping by category (Books, Annotations, Vocabulary, Notes)
    - Incremental index update on entity changes
    - Result navigation data for locating matches in books/panels
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str) -> SearchResults:
        """Execute a unified full-text search across all indexed content.

        Translates the user query into FTS5 syntax, searches all FTS tables,
        and returns results ranked by relevance and grouped by category.

        Args:
            query: The user's search query. Supports operators:
                - Exact phrase: "hello world"
                - AND (default): word1 word2
                - OR: word1 OR word2
                - Exclude: -word (removes matches containing word)

        Returns:
            SearchResults containing matched items grouped by category.
        """
        if not query or not query.strip():
            return SearchResults(query=query, items=[], total_count=0)

        fts_query = self._translate_query(query)

        if not fts_query.strip():
            return SearchResults(query=query, items=[], total_count=0)

        items: list[SearchResultItem] = []

        # Search books
        items.extend(self._search_books(fts_query))
        # Search annotations (split into Annotations and Notes categories)
        items.extend(self._search_annotations(fts_query))
        # Search vocabulary
        items.extend(self._search_vocabulary(fts_query))

        # Sort by relevance rank (lower rank = more relevant in FTS5 bm25)
        items.sort(key=lambda x: x.rank)

        return SearchResults(
            query=query,
            items=items,
            total_count=len(items),
        )

    def update_index(self, entity_type: str, entity_id: str) -> None:
        """Trigger an incremental index update for a specific entity.

        Since FTS5 sync triggers handle INSERT/UPDATE/DELETE automatically,
        this method forces a rebuild of the specific FTS table index if needed.
        In normal operation, the triggers maintain the index within 1 second.

        For manual index refresh scenarios (e.g., bulk import without triggers),
        this method rebuilds the relevant FTS table.

        Args:
            entity_type: The entity type ("book", "annotation", "vocabulary").
            entity_id: The ID of the entity that changed (currently unused
                since triggers handle sync, but reserved for future use).
        """
        rebuild_map = {
            "book": "INSERT INTO books_fts(books_fts) VALUES('rebuild');",
            "annotation": "INSERT INTO annotations_fts(annotations_fts) VALUES('rebuild');",
            "vocabulary": "INSERT INTO vocabulary_fts(vocabulary_fts) VALUES('rebuild');",
        }

        stmt = rebuild_map.get(entity_type)
        if stmt is None:
            return

        with self._engine.connect() as conn:
            conn.execute(text(stmt))
            conn.commit()

    # ------------------------------------------------------------------
    # Private: FTS5 query translation
    # ------------------------------------------------------------------

    def _translate_query(self, query: str) -> str:
        """Translate user search query to FTS5 query syntax.

        Handles:
        - Exact phrases in double quotes → passed through as-is (FTS5 supports "...")
        - OR operator → passed through (FTS5 supports OR)
        - Exclude with minus prefix → translated to NOT
        - Default conjunction is AND (implicit in FTS5 with spaces)

        Args:
            query: The raw user query string.

        Returns:
            A valid FTS5 query string.
        """
        # Extract quoted phrases first to protect them
        phrases: list[str] = []
        phrase_pattern = re.compile(r'"([^"]*)"')

        def replace_phrase(match: re.Match) -> str:
            phrases.append(f'"{match.group(1)}"')
            return f"__PHRASE_{len(phrases) - 1}__"

        working = phrase_pattern.sub(replace_phrase, query)

        # Tokenize the remaining parts
        tokens = working.split()
        fts_tokens: list[str] = []

        for token in tokens:
            # Check for phrase placeholder
            if token.startswith("__PHRASE_") and token.endswith("__"):
                idx = int(token[9:-2])
                fts_tokens.append(phrases[idx])
            # OR operator
            elif token.upper() == "OR":
                fts_tokens.append("OR")
            # AND operator (explicit)
            elif token.upper() == "AND":
                fts_tokens.append("AND")
            # Exclude operator (minus prefix)
            elif token.startswith("-") and len(token) > 1:
                excluded_term = token[1:]
                fts_tokens.append(f"NOT {excluded_term}")
            else:
                # Regular term — clean non-alphanumeric chars that aren't valid in FTS5
                cleaned = self._clean_token(token)
                if cleaned:
                    fts_tokens.append(cleaned)

        return " ".join(fts_tokens)

    def _clean_token(self, token: str) -> str:
        """Remove characters that are not valid in FTS5 query terms.

        Keeps alphanumeric, underscore, and unicode word characters.
        Strips leading/trailing punctuation.

        Args:
            token: A single search term.

        Returns:
            The cleaned token, or empty string if nothing remains.
        """
        # Remove leading/trailing non-word characters but keep internal ones
        cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", token)
        return cleaned

    # ------------------------------------------------------------------
    # Private: Category-specific search methods
    # ------------------------------------------------------------------

    def _search_books(self, fts_query: str) -> list[SearchResultItem]:
        """Search the books_fts table for matching books.

        Args:
            fts_query: The translated FTS5 query.

        Returns:
            List of SearchResultItem in the Books category.
        """
        sql = text(
            """
            SELECT
                b.id,
                b.title,
                b.author,
                bm25(books_fts) as rank
            FROM books_fts
            JOIN books b ON books_fts.rowid = b.rowid
            WHERE books_fts MATCH :query
            ORDER BY rank
            LIMIT 50
            """
        )

        items: list[SearchResultItem] = []
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sql, {"query": fts_query})
                for row in result:
                    snippet = f"{row.title}"
                    if row.author:
                        snippet += f" by {row.author}"

                    items.append(
                        SearchResultItem(
                            entity_id=row.id,
                            category=SearchCategory.BOOKS,
                            title=row.title or "",
                            snippet=snippet,
                            rank=row.rank,
                            book_id=row.id,
                            position_data=None,
                        )
                    )
        except Exception:
            # FTS5 query syntax errors are caught here gracefully
            pass

        return items

    def _search_annotations(self, fts_query: str) -> list[SearchResultItem]:
        """Search the annotations_fts table for matching annotations and notes.

        Annotations with note_content are categorized as Notes;
        others are categorized as Annotations.

        Args:
            fts_query: The translated FTS5 query.

        Returns:
            List of SearchResultItem in Annotations or Notes categories.
        """
        sql = text(
            """
            SELECT
                a.id,
                a.book_id,
                a.selected_text,
                a.note_content,
                a.position_data,
                a.type,
                bm25(annotations_fts) as rank
            FROM annotations_fts
            JOIN annotations a ON annotations_fts.rowid = a.rowid
            WHERE annotations_fts MATCH :query
            ORDER BY rank
            LIMIT 50
            """
        )

        items: list[SearchResultItem] = []
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sql, {"query": fts_query})
                for row in result:
                    # Determine category based on whether it's a note-type annotation
                    has_note = bool(row.note_content and row.note_content.strip())
                    is_note_type = row.type in ("note", "comment")

                    if is_note_type or has_note:
                        category = SearchCategory.NOTES
                        title = (row.note_content or row.selected_text or "")[:80]
                        snippet = row.note_content or row.selected_text or ""
                    else:
                        category = SearchCategory.ANNOTATIONS
                        title = (row.selected_text or "")[:80]
                        snippet = row.selected_text or ""

                    # Truncate snippet for display
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."

                    items.append(
                        SearchResultItem(
                            entity_id=row.id,
                            category=category,
                            title=title,
                            snippet=snippet,
                            rank=row.rank,
                            book_id=row.book_id,
                            position_data=row.position_data,
                        )
                    )
        except Exception:
            pass

        return items

    def _search_vocabulary(self, fts_query: str) -> list[SearchResultItem]:
        """Search the vocabulary_fts table for matching vocabulary entries.

        Args:
            fts_query: The translated FTS5 query.

        Returns:
            List of SearchResultItem in the Vocabulary category.
        """
        sql = text(
            """
            SELECT
                v.id,
                v.word,
                v.definition,
                v.example_sentence,
                v.book_id,
                v.position_data,
                bm25(vocabulary_fts) as rank
            FROM vocabulary_fts
            JOIN vocabulary_entries v ON vocabulary_fts.rowid = v.rowid
            WHERE vocabulary_fts MATCH :query
            ORDER BY rank
            LIMIT 50
            """
        )

        items: list[SearchResultItem] = []
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sql, {"query": fts_query})
                for row in result:
                    # Build a snippet from definition and example
                    snippet_parts = []
                    if row.definition:
                        snippet_parts.append(row.definition)
                    if row.example_sentence:
                        snippet_parts.append(f"e.g. {row.example_sentence}")
                    snippet = " — ".join(snippet_parts) if snippet_parts else row.word

                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."

                    items.append(
                        SearchResultItem(
                            entity_id=row.id,
                            category=SearchCategory.VOCABULARY,
                            title=row.word or "",
                            snippet=snippet,
                            rank=row.rank,
                            book_id=row.book_id,
                            position_data=row.position_data,
                        )
                    )
        except Exception:
            pass

        return items
