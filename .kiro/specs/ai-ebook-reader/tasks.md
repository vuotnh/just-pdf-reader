# Implementation Plan: AI Ebook Reader & Vocabulary Learning Platform

## Overview

This implementation plan follows the MVP phasing strategy: Phase 1 (Library, PDF, EPUB, Highlight, Bookmark, Dictionary), Phase 2 (Vocabulary, Flashcard, Spaced Repetition), Phase 3 (Knowledge Graph, Plugin System), Phase 4 (Sync, Plugin Marketplace). Each phase builds incrementally on the previous, with property-based tests validating correctness properties from the design document.

The architecture follows Clean Architecture: Presentation (QML) → Application (Services) → Domain (Models) → Infrastructure (Database, Parsers, Dictionary APIs).

## Tasks

- [x] 1. Project scaffolding and database foundation
  - [x] 1.1 Create project directory structure and core configuration
    - Create directory structure: `src/{presentation,application,domain,infrastructure}`, `tests/{unit,property,integration}`, `migrations/`, `resources/`
    - Create `pyproject.toml` with dependencies: PySide6, PyMuPDF, SQLAlchemy, alembic, hypothesis, pytest, asyncio
    - Create `conftest.py` with in-memory SQLite fixtures, Hypothesis profiles (ci/dev/quick)
    - Create `src/__init__.py`, `src/main.py` entry point skeleton
    - _Requirements: 12.1, 13.1_

  - [x] 1.2 Implement domain models and enums
    - Create `src/domain/models.py` with Python dataclasses: Book, Annotation, Bookmark, Comment, Collection, Tag, ReadingHistory, VocabularyEntry, ReviewCard, ReviewLog, KnowledgeNode, KnowledgeLink, DictCache
    - Create `src/domain/enums.py` with enums: BookFormat, AnnotationType, HighlightColor, MasteryLevel, Rating, SortCriterion, CardType, SRAlgorithm
    - Create `src/domain/value_objects.py` with: TextPosition, ReadingPosition, BookFilter, VocabFilter, DeckFilter, GraphFilter
    - _Requirements: 1.1, 5.1, 7.4, 8.1_

  - [x] 1.3 Implement SQLAlchemy ORM models and database setup
    - Create `src/infrastructure/database/models.py` with all SQLAlchemy ORM models matching the ER diagram from the design
    - Create `src/infrastructure/database/engine.py` with engine creation, WAL mode pragmas, foreign keys, synchronous=NORMAL
    - Create `src/infrastructure/database/session.py` with session factory and context manager
    - Implement association tables for many-to-many: book_collections, book_tags, annotation_tags, vocabulary_tags
    - _Requirements: 13.1, 13.3_

  - [x] 1.4 Implement FTS5 virtual tables and sync triggers
    - Create `src/infrastructure/database/fts.py` with DDL for books_fts, annotations_fts, vocabulary_fts virtual tables
    - Implement after-insert, after-update, after-delete triggers for FTS5 sync
    - Create utility function to rebuild FTS index from existing data
    - _Requirements: 10.1, 10.6_

  - [x] 1.5 Implement Alembic schema migration infrastructure
    - Initialize Alembic with `migrations/` directory and `alembic.ini`
    - Create initial migration from ORM models
    - Implement startup migration check in `src/infrastructure/database/migrations.py` (auto-run `alembic upgrade head`)
    - _Requirements: 13.6_

  - [x]* 1.6 Write property test for schema migration data preservation
    - **Property 28: Schema migration data preservation**
    - **Validates: Requirements 13.6**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Library Manager implementation
  - [x] 3.1 Implement Library repository layer
    - Create `src/infrastructure/repositories/book_repository.py` with CRUD operations for Book, Collection, Tag
    - Implement sorting by all criteria: title, author, date_added, last_read, file_size
    - Implement filtering by tag, collection, favorite status
    - Implement reading history recording and last-read position persistence
    - _Requirements: 1.7, 1.8, 1.9, 1.10_

  - [x] 3.2 Implement file import and metadata extraction
    - Create `src/infrastructure/parsers/metadata_extractor.py` with format-specific extractors
    - Implement PDF metadata extraction via PyMuPDF (`doc.metadata`)
    - Implement EPUB metadata extraction (parse OPF content.opf)
    - Implement fallback logic: on extraction failure, use filename as title
    - Implement file hash computation for deduplication
    - Implement cover image extraction (PDF first page thumbnail, EPUB cover image)
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 3.3 Implement LibraryService application layer
    - Create `src/application/services/library_service.py` implementing ILibraryService protocol
    - Implement `import_files()` with format filtering (.pdf, .epub, .azw3 only)
    - Implement `import_folder()` with recursive scan
    - Implement collection CRUD (create, add/remove books)
    - Implement tag management (add/remove tags to books)
    - Implement favorite toggling and reading history recording
    - Implement FTS5 index update on import
    - _Requirements: 1.1–1.10_

  - [x]* 3.4 Write property tests for Library Manager
    - **Property 1: Import filters by supported format**
    - **Property 2: Metadata extraction fallback preserves filename**
    - **Property 3: Collection membership consistency**
    - **Property 4: Tag search completeness**
    - **Property 5: Library sorting correctness**
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5, 1.9, 1.10**

  - [x] 3.5 Implement Library QML controller
    - Create `src/presentation/controllers/library_controller.py` as QObject with Properties, Slots, Signals
    - Expose book list model (QAbstractListModel subclass) for grid/list view binding
    - Implement slots: importFiles, importFolder, createCollection, addTag, setFavorite, openBook
    - Implement signals: booksChanged, importProgress, importComplete
    - _Requirements: 1.8, 14.1_

  - [x] 3.6 Implement Library QML views
    - Create `src/presentation/qml/LibraryView.qml` with grid view (cover thumbnails) and list view (metadata columns)
    - Create `src/presentation/qml/LibraryToolbar.qml` with sort, filter, view-toggle, import buttons
    - Create `src/presentation/qml/CollectionPanel.qml` for collection management
    - Implement drag-and-drop import from file manager
    - _Requirements: 1.8, 1.9, 1.10, 14.1_

- [ ] 4. PDF Reader implementation
  - [x] 4.1 Implement PDF reader backend
    - Create `src/infrastructure/readers/pdf_reader_backend.py` using PyMuPDF
    - Implement page rendering to QPixmap via `page.get_pixmap(matrix=zoom_matrix)`
    - Implement LRU page cache (20 pages) with pre-rendering of ±3 adjacent pages
    - Implement zoom level clamping (25% to 400%) with fit-width and fit-page presets
    - Implement continuous scroll mode and single-page mode
    - Implement text extraction via `page.get_text("dict")` for selection support
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.2 Implement PDF TOC extraction and text search
    - Implement TOC extraction from PDF document outline (`doc.get_toc()`)
    - Implement full-text search across all pages with match positions
    - Implement search result navigation (next/previous match)
    - _Requirements: 2.5, 2.6_

  - [-] 4.3 Implement PDF Reader QML controller and view
    - Create `src/presentation/controllers/pdf_reader_controller.py` as QObject
    - Create QML Image Provider for rendering pages to QML
    - Implement slots: openPdf, setZoom, setPageMode, search, nextMatch, prevMatch
    - Create `src/presentation/qml/PDFReaderView.qml` with page display, scroll handling, zoom controls
    - Create `src/presentation/qml/TOCPanel.qml` for document outline navigation
    - _Requirements: 2.1–2.6, 14.1_

  - [x]* 4.4 Write property tests for PDF Reader
    - **Property 7: Zoom level clamping**
    - **Property 8: Text search finds all occurrences**
    - **Validates: Requirements 2.2, 2.6**

- [ ] 5. EPUB Reader implementation
  - [x] 5.1 Implement EPUB parser and reader backend
    - Create `src/infrastructure/readers/epub_reader_backend.py`
    - Implement EPUB zip extraction and structure parsing (OPF, NCX/NAV)
    - Implement HTML chapter extraction with resource resolution (images, CSS)
    - Implement CSS injection for font settings, theme (dark mode), annotation highlights
    - Implement pagination mode (CSS column splitting) and continuous scroll mode
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [-] 5.2 Implement QWebEngine integration and JavaScript bridge
    - Create `src/infrastructure/readers/webengine_bridge.py` using QWebChannel
    - Implement JavaScript bridge for text selection events, annotation rendering
    - Implement font settings application (family, size 8–48pt, line spacing)
    - Implement dark mode CSS inversion preserving image appearance
    - Implement reading position save/restore (chapter + scroll offset)
    - _Requirements: 3.3, 3.4, 3.7, 3.8, 3.10_

  - [-] 5.3 Implement EPUB TOC and search
    - Implement NCX/NAV navigation structure parsing for table of contents
    - Implement cross-chapter text search with match highlighting
    - _Requirements: 3.5, 3.6_

  - [x] 5.4 Implement EPUB Reader QML controller and view
    - Create `src/presentation/controllers/epub_reader_controller.py` as QObject
    - Implement slots: openEpub, setFont, setTheme, setPageMode, search, addBookmark
    - Create `src/presentation/qml/EPUBReaderView.qml` with QWebEngineView and controls
    - Create `src/presentation/qml/ReaderSettings.qml` for font/theme configuration
    - _Requirements: 3.1–3.10, 14.1_

  - [x]* 5.5 Write property tests for EPUB Reader
    - **Property 6: Reading position round-trip**
    - **Property 12: Font settings CSS generation**
    - **Validates: Requirements 1.7, 3.3, 3.10**

- [ ] 6. Annotation System implementation
  - [x] 6.1 Implement Annotation repository and service
    - Create `src/infrastructure/repositories/annotation_repository.py` with CRUD for Annotation, Comment, Bookmark
    - Create `src/application/services/annotation_service.py` implementing IAnnotationService
    - Implement create annotation with exact text position, book reference, timestamp, type, color
    - Implement comment threading (append comment with timestamp to annotation)
    - Implement tag association for annotations
    - Implement delete annotation with cascade (comments, tag associations)
    - Implement Markdown export for all annotations of a book
    - _Requirements: 5.1–5.8_

  - [-] 6.2 Implement Annotation QML integration
    - Create `src/presentation/controllers/annotation_controller.py` as QObject
    - Implement context menu display on text selection (highlight, underline, note, copy, dictionary)
    - Implement annotation panel showing all annotations grouped by chapter/page
    - Create `src/presentation/qml/AnnotationPanel.qml` with chronological annotation list
    - Create `src/presentation/qml/ContextMenu.qml` for text selection actions
    - Wire annotation rendering into both PDF (overlay coordinates) and EPUB (CSS highlight injection)
    - _Requirements: 2.8, 2.9, 3.7, 3.8, 5.2, 5.3, 5.6_

  - [ ]* 6.3 Write property tests for Annotation System
    - **Property 9: Annotation persistence round-trip**
    - **Property 10: Annotation export contains all annotations**
    - **Property 11: Bookmark persistence round-trip**
    - **Property 27: Annotation deletion completeness**
    - **Validates: Requirements 2.7, 2.9, 2.10, 3.8, 3.9, 5.1, 5.7, 5.8**

- [ ] 7. Dictionary Engine implementation
  - [-] 7.1 Implement Dictionary lookup chain and caching
    - Create `src/infrastructure/dictionary/dict_cache.py` for SQLite-based cache (word+language key)
    - Create `src/infrastructure/dictionary/stardict_reader.py` for local StarDict format parsing
    - Create `src/infrastructure/dictionary/online_api.py` with clients for Oxford, Cambridge, Merriam Webster, Wiktionary
    - Implement chain-of-responsibility: cache → StarDict → online API (configurable priority)
    - Implement result normalization to DictEntry (word, IPA, parts of speech, definitions, examples, synonyms)
    - Implement cache population on successful lookup from any non-cache source
    - _Requirements: 6.1–6.8_

  - [~] 7.2 Implement DictionaryService and QML integration
    - Create `src/application/services/dictionary_service.py` implementing IDictionaryService
    - Create `src/presentation/controllers/dictionary_controller.py` as QObject
    - Implement double-click word lookup triggering popup within 100ms target
    - Create `src/presentation/qml/DictionaryPopup.qml` with pronunciation, definitions, examples, synonyms, source selector
    - Implement "Save to Vocabulary" button in popup
    - _Requirements: 6.1–6.8, 12.2_

  - [ ]* 7.3 Write property tests for Dictionary Engine
    - **Property 13: Dictionary lookup chain priority**
    - **Property 14: Dictionary cache population**
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [~] 8. Checkpoint - Ensure Phase 1 tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. AZW3 Reader implementation
  - [~] 9.1 Implement AZW3 conversion pipeline
    - Create `src/infrastructure/readers/azw3_reader_backend.py`
    - Implement Calibre ebook-convert subprocess call (AZW3 → HTML)
    - Implement conversion progress reporting via stdout parsing
    - Implement file-based conversion cache at `~/.ai-ebook-reader/cache/azw3/{hash}/`
    - Implement error handling for DRM-locked and corrupted files with descriptive messages
    - Reuse EPUB rendering pipeline (QWebEngine + CSS injection) after conversion
    - _Requirements: 4.1–4.5_

  - [ ]* 9.2 Write unit tests for AZW3 Reader
    - Test conversion pipeline with sample AZW3 files
    - Test cache hit/miss behavior
    - Test error handling for DRM and corruption
    - _Requirements: 4.1–4.4_

- [ ] 10. Vocabulary Builder implementation
  - [~] 10.1 Implement Vocabulary repository and service
    - Create `src/infrastructure/repositories/vocabulary_repository.py` with CRUD for VocabularyEntry
    - Create `src/application/services/vocabulary_service.py` implementing IVocabularyService
    - Implement save_word with all fields (word, definition, pronunciation, example, source book, position)
    - Implement auto-assignment to default review queue with due_date = today
    - Implement mastery level tracking (New, Learning, Reviewing, Mastered)
    - Implement vocabulary entry editing and deletion with cascade to review cards/logs
    - Implement export to CSV and Anki-compatible format
    - _Requirements: 7.1–7.7_

  - [~] 10.2 Implement Vocabulary QML panel
    - Create `src/presentation/controllers/vocabulary_controller.py` as QObject
    - Create `src/presentation/qml/VocabularyPanel.qml` with word list sorted by date, filter by book/tag/mastery
    - Implement edit/delete vocabulary entry UI
    - Implement export button with format selection
    - _Requirements: 7.3–7.7, 14.3_

  - [ ]* 10.3 Write property tests for Vocabulary Builder
    - **Property 15: Vocabulary save includes all fields**
    - **Property 16: Vocabulary deletion cascades to review schedules**
    - **Validates: Requirements 7.1, 7.2, 7.6**

- [ ] 11. Spaced Repetition Engine implementation
  - [~] 11.1 Implement FSRS algorithm
    - Create `src/domain/algorithms/fsrs.py` implementing ISchedulingAlgorithm
    - Implement retrievability calculation: R(t, S) = (1 + t/(9*S))^(-1)
    - Implement stability update for successful review (S'_recall) and failed review (S'_forget)
    - Implement difficulty update with clamping [1, 10]
    - Implement initial stability by rating using default 17-weight parameters
    - Implement interval calculation from desired retention (default 0.9)
    - _Requirements: 8.1, 8.3_

  - [~] 11.2 Implement SM2 algorithm
    - Create `src/domain/algorithms/sm2.py` implementing ISchedulingAlgorithm
    - Implement ease factor update with floor at 1.3
    - Implement interval progression: 1 day → 6 days → prev * EF
    - Implement reset on failure (repetitions = 0, interval = 1 day)
    - _Requirements: 8.1, 8.3_

  - [~] 11.3 Implement SpacedRepetitionService
    - Create `src/application/services/spaced_repetition_service.py` implementing ISpacedRepetitionService
    - Implement start_session with card ordering (overdue first, then due today)
    - Implement rate_card dispatching to selected algorithm (FSRS or SM2)
    - Implement session statistics (cards reviewed, accuracy, time spent)
    - Implement daily stats (due today, reviewed, new cards, 7-day forecast)
    - Implement algorithm switching with schedule recalculation
    - Implement review modes: flashcard, multiple choice, typing, cloze deletion
    - _Requirements: 8.1–8.7_

  - [~] 11.4 Implement Review Session QML view
    - Create `src/presentation/controllers/review_controller.py` as QObject
    - Create `src/presentation/qml/ReviewSessionView.qml` with card display, rating buttons, progress
    - Create `src/presentation/qml/ReviewStatsView.qml` with daily stats and 7-day forecast chart
    - Implement review mode switching UI (flashcard, MCQ, typing, cloze)
    - _Requirements: 8.2–8.6, 14.1_

  - [ ]* 11.5 Write property tests for Spaced Repetition
    - **Property 17: FSRS interval ordering by rating**
    - **Property 18: SM2 ease factor bounds**
    - **Property 19: FSRS stability increases on successful review**
    - **Property 20: Review session card ordering**
    - **Property 21: Review statistics accuracy**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.5**

- [~] 12. Checkpoint - Ensure Phase 2 tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Search Engine implementation
  - [~] 13.1 Implement SearchService with FTS5
    - Create `src/application/services/search_service.py` implementing ISearchService
    - Implement unified search across books_fts, annotations_fts, vocabulary_fts
    - Implement search operators: exact phrase (quotes), AND, OR, exclude (minus)
    - Implement result ranking by relevance and grouping by category (Books, Annotations, Vocabulary, Notes)
    - Implement incremental index update on entity changes (within 1 second)
    - Implement result navigation to exact location in corresponding book/panel
    - _Requirements: 10.1–10.6_

  - [~] 13.2 Implement Search QML integration
    - Create `src/presentation/controllers/search_controller.py` as QObject
    - Create `src/presentation/qml/SearchPanel.qml` with search input, results grouped by category
    - Implement keyboard shortcut for global search
    - Implement click-to-navigate on search results
    - _Requirements: 10.1, 10.3, 10.4, 14.2, 14.6_

  - [ ]* 13.3 Write property tests for Search Engine
    - **Property 24: FTS5 search completeness**
    - **Property 25: Search operator semantics**
    - **Validates: Requirements 10.1, 10.5**

- [ ] 14. Knowledge Graph implementation
  - [~] 14.1 Implement KnowledgeGraphService
    - Create `src/infrastructure/repositories/knowledge_repository.py` with CRUD for KnowledgeNode, KnowledgeLink
    - Create `src/application/services/knowledge_graph_service.py` implementing IKnowledgeGraphService
    - Implement graph construction from books, annotations, vocabulary, tags as nodes
    - Implement bidirectional backlink creation and querying
    - Implement graph filtering by tag or book
    - Implement auto-link generation (same-book, shared-tag connections)
    - _Requirements: 9.1–9.5_

  - [~] 14.2 Implement Knowledge Graph QML visualization
    - Create `src/presentation/controllers/knowledge_graph_controller.py` as QObject
    - Create `src/presentation/qml/KnowledgeGraphView.qml` with force-directed graph layout
    - Implement node click navigation to corresponding entity
    - Implement graph filter controls (by tag, book)
    - Implement graph update within 500ms of new data
    - _Requirements: 9.1–9.5, 14.1_

  - [ ]* 14.3 Write property tests for Knowledge Graph
    - **Property 22: Knowledge Graph backlink bidirectionality**
    - **Property 23: Knowledge Graph filter consistency**
    - **Validates: Requirements 9.2, 9.5**

- [ ] 15. Plugin System implementation
  - [~] 15.1 Implement Plugin loader and hook registry
    - Create `src/infrastructure/plugins/plugin_loader.py` with plugin discovery, validation, loading
    - Create `src/infrastructure/plugins/hook_registry.py` with hook registration and dispatch
    - Implement plugin structure validation (plugin.json schema check)
    - Implement plugin isolation (restricted globals, file I/O to own directory, network permission)
    - Implement plugin execution timeout (5 seconds) and error catching
    - Implement plugin enable/disable without data deletion
    - _Requirements: 11.1–11.6_

  - [~] 15.2 Implement PluginService and QML settings
    - Create `src/application/services/plugin_service.py` implementing IPluginService
    - Create `src/presentation/controllers/plugin_controller.py` as QObject
    - Create `src/presentation/qml/PluginSettings.qml` with installed plugins list, status, config
    - Implement plugin install, enable, disable, uninstall flows
    - Implement hook execution for: on_word_lookup, on_text_process, on_export, on_import, on_ui_extend
    - _Requirements: 11.1–11.6_

  - [ ]* 15.3 Write property tests for Plugin System
    - **Property 26: Plugin error isolation**
    - **Validates: Requirements 11.4, 11.5**

- [~] 16. Checkpoint - Ensure Phase 3 tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. UI Layout, Performance, and Data Persistence
  - [~] 17.1 Implement main application window and layout
    - Create `src/presentation/qml/MainWindow.qml` with layout: Toolbar (top), Navigation Panel (left), Reader Area (center), Side Panel (right), Status Bar (bottom)
    - Implement panel toggle (show/hide) for Navigation Panel and Side Panel
    - Implement panel resize with minimum 200px width enforcement
    - Implement layout state persistence (panel open/closed, widths) between sessions
    - Create `src/presentation/qml/Toolbar.qml` with primary action buttons
    - Create `src/presentation/qml/StatusBar.qml` with reading progress and status info
    - _Requirements: 14.1–14.5_

  - [~] 17.2 Implement keyboard shortcuts and navigation
    - Create `src/presentation/shortcuts.py` with keyboard shortcut registry
    - Implement shortcuts for: open book, toggle panels, create bookmark, search, navigate pages
    - Integrate shortcuts with QML action handlers
    - _Requirements: 14.6_

  - [~] 17.3 Implement application lifecycle and data persistence
    - Create `src/application/app.py` main application class with startup/shutdown lifecycle
    - Implement startup: migration check, WAL integrity check, load settings, display main window within 1s
    - Implement shutdown: flush pending changes, save layout state, close database
    - Implement crash recovery: WAL journal recovery on startup, integrity check
    - Implement confirmation dialogs for destructive actions (delete book, annotation, vocabulary)
    - Implement database backup to user-specified location
    - _Requirements: 12.1, 13.1–13.6_

  - [~] 17.4 Implement Reader Factory and book opening orchestration
    - Create `src/application/services/reader_service.py` implementing IReaderService
    - Implement ReaderFactory pattern: dispatch to PDF/EPUB/AZW3 backend by file extension
    - Wire reader opening through LibraryService (record_open, restore last position)
    - Integrate annotation system with all reader backends
    - Integrate dictionary popup with text selection in all readers
    - _Requirements: 1.7, 2.1, 3.1, 4.1_

  - [ ]* 17.5 Write property tests for UI and persistence
    - **Property 29: Panel layout state persistence**
    - **Property 30: Panel minimum width enforcement**
    - **Validates: Requirements 14.4, 14.5**

- [~] 18. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at each phase boundary
- Property tests validate universal correctness properties from the design document (30 properties total)
- Unit tests validate specific examples and edge cases
- The implementation uses Python throughout (PySide6, SQLAlchemy, PyMuPDF, Hypothesis)
- Phase 4 (Sync, Plugin Marketplace) is deferred and not included in this implementation plan

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5"] },
    { "id": 3, "tasks": ["1.6"] },
    { "id": 4, "tasks": ["3.1", "3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["3.4", "3.5"] },
    { "id": 7, "tasks": ["3.6", "4.1"] },
    { "id": 8, "tasks": ["4.2", "5.1"] },
    { "id": 9, "tasks": ["4.3", "5.2", "5.3"] },
    { "id": 10, "tasks": ["4.4", "5.4"] },
    { "id": 11, "tasks": ["5.5", "6.1"] },
    { "id": 12, "tasks": ["6.2", "7.1"] },
    { "id": 13, "tasks": ["6.3", "7.2"] },
    { "id": 14, "tasks": ["7.3", "9.1"] },
    { "id": 15, "tasks": ["9.2", "10.1"] },
    { "id": 16, "tasks": ["10.2", "11.1", "11.2"] },
    { "id": 17, "tasks": ["10.3", "11.3"] },
    { "id": 18, "tasks": ["11.4"] },
    { "id": 19, "tasks": ["11.5", "13.1"] },
    { "id": 20, "tasks": ["13.2", "14.1"] },
    { "id": 21, "tasks": ["13.3", "14.2"] },
    { "id": 22, "tasks": ["14.3", "15.1"] },
    { "id": 23, "tasks": ["15.2"] },
    { "id": 24, "tasks": ["15.3", "17.1"] },
    { "id": 25, "tasks": ["17.2", "17.3"] },
    { "id": 26, "tasks": ["17.4"] },
    { "id": 27, "tasks": ["17.5"] }
  ]
}
```
