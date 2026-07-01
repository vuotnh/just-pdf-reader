# Requirements Document

## Introduction

AI Ebook Reader & Vocabulary Learning Platform là một ứng dụng desktop kết hợp các tính năng tốt nhất của Obsidian (quản lý tri thức), Kindle (đọc sách), Zotero (quản lý tài liệu nghiên cứu) và Anki (flashcard/spaced repetition). Ứng dụng phục vụ ba nhóm người dùng chính: người học ngoại ngữ, nhà nghiên cứu, và người đọc sách chuyên sâu.

**Tech Stack:** PySide6 + Qt Quick (QML), PyMuPDF, QWebEngine, SQLite, SQLAlchemy, asyncio, PyInstaller.

**MVP Phasing:**
- Phase 1: Library, PDF Reader, EPUB Reader, Highlight, Bookmark, Dictionary
- Phase 2: Vocabulary Builder, Flashcard, Spaced Repetition
- Phase 3: Knowledge Graph, Plugin System
- Phase 4: Sync, Plugin Marketplace

## Glossary

- **Application**: Ứng dụng AI Ebook Reader & Vocabulary Learning Platform
- **Library_Manager**: Module quản lý thư viện sách, bao gồm import, scan, metadata, collections
- **PDF_Reader**: Module đọc và hiển thị file PDF sử dụng PyMuPDF engine
- **EPUB_Reader**: Module đọc và hiển thị file EPUB sử dụng QWebEngine + EPUB parser
- **AZW3_Reader**: Module đọc file AZW3 thông qua pipeline chuyển đổi Calibre parser → internal HTML → QWebEngine
- **Annotation_System**: Hệ thống quản lý highlight, underline, note, comment, bookmark, tag
- **Dictionary_Engine**: Module tra từ điển hỗ trợ local cache và online API (Oxford, Cambridge, Merriam Webster, Wiktionary, StarDict)
- **Vocabulary_Builder**: Module xây dựng vốn từ vựng từ việc tra cứu trong quá trình đọc sách
- **Spaced_Repetition_Engine**: Module ôn tập từ vựng sử dụng thuật toán SM2 và FSRS
- **Knowledge_Graph**: Module quản lý tri thức với backlink và tag graph
- **Search_Engine**: Module tìm kiếm toàn cục sử dụng SQLite FTS5
- **Sync_Engine**: Module đồng bộ dữ liệu giữa các thiết bị (future)
- **Plugin_System**: Hệ thống plugin mở rộng chức năng ứng dụng
- **Book**: Một tài liệu (PDF, EPUB, hoặc AZW3) được import vào Library
- **Collection**: Nhóm sách do người dùng tạo để tổ chức thư viện
- **Annotation**: Bất kỳ đánh dấu nào trên nội dung sách (highlight, underline, note, comment)
- **Flashcard**: Thẻ ghi nhớ chứa từ vựng với mặt trước (từ) và mặt sau (nghĩa, ví dụ, phát âm)
- **Review_Session**: Phiên ôn tập từ vựng theo thuật toán spaced repetition
- **User**: Người sử dụng ứng dụng

## Requirements

---

### Requirement 1: Library Import và Quản Lý Sách

**User Story:** As a User, I want to import and organize my ebook collection, so that I can easily find and access my reading materials.

#### Acceptance Criteria

1. WHEN a User selects files or a folder for import, THE Library_Manager SHALL scan and import all supported files (PDF, EPUB, AZW3) into the library database.
2. WHEN a Book is imported, THE Library_Manager SHALL extract metadata including title, author, publisher, language, page count, and cover image from the file.
3. IF metadata extraction fails for a Book, THEN THE Library_Manager SHALL create a library entry using the filename as the title and allow manual metadata editing.
4. WHEN a User creates a Collection, THE Library_Manager SHALL store the Collection and allow the User to add or remove Books from the Collection.
5. WHEN a User adds a tag to a Book, THE Library_Manager SHALL associate the tag with the Book and make the Book searchable by that tag.
6. WHEN a User marks a Book as favorite, THE Library_Manager SHALL persist the favorite status and display the Book in the Favorites view.
7. WHEN a User opens a Book, THE Library_Manager SHALL record the access timestamp in reading history and update the last-read position.
8. THE Library_Manager SHALL display the library in both grid view (with cover thumbnails) and list view (with metadata columns).
9. WHEN a User sorts the library, THE Library_Manager SHALL sort Books by the selected criterion (title, author, date added, last read, file size).
10. WHEN a User filters the library by tag or Collection, THE Library_Manager SHALL display only Books matching the filter criteria.

---

### Requirement 2: PDF Reader

**User Story:** As a User, I want to read PDF documents with standard reading features, so that I can comfortably study and annotate PDF materials.

#### Acceptance Criteria

1. WHEN a User opens a PDF file, THE PDF_Reader SHALL render the first page (or last-read page) within 500 milliseconds.
2. THE PDF_Reader SHALL support zoom levels from 25% to 400% with fit-width and fit-page presets.
3. WHEN a User scrolls through a PDF, THE PDF_Reader SHALL render each visible page within 16 milliseconds to maintain 60fps scrolling.
4. THE PDF_Reader SHALL support both continuous scroll mode and single-page mode.
5. WHEN a User activates the Table of Contents panel, THE PDF_Reader SHALL display the document outline extracted from the PDF structure and allow navigation to any section.
6. WHEN a User searches for text in a PDF, THE PDF_Reader SHALL highlight all occurrences and allow navigation between matches.
7. WHEN a User adds a bookmark to a page, THE PDF_Reader SHALL persist the bookmark with page number and optional label.
8. WHEN a User selects text in a PDF, THE PDF_Reader SHALL display a context menu with options to highlight, underline, add note, copy, and look up in dictionary.
9. WHEN a User applies a highlight to selected text, THE PDF_Reader SHALL render the highlight with the chosen color and persist the annotation.
10. WHEN a User requests annotation export, THE PDF_Reader SHALL export all annotations for the current Book in Markdown format.

---

### Requirement 3: EPUB Reader

**User Story:** As a User, I want to read EPUB books with customizable reading experience, so that I can read comfortably for extended periods.

#### Acceptance Criteria

1. WHEN a User opens an EPUB file, THE EPUB_Reader SHALL parse the EPUB structure and render the content using QWebEngine within 500 milliseconds.
2. THE EPUB_Reader SHALL support both pagination mode (page-by-page) and continuous scroll mode.
3. WHEN a User changes font settings, THE EPUB_Reader SHALL apply the selected font family, font size (range 8pt to 48pt), and line spacing immediately.
4. WHEN a User activates dark mode, THE EPUB_Reader SHALL invert the content colors while preserving image appearance.
5. WHEN a User activates the Table of Contents panel, THE EPUB_Reader SHALL display the navigation structure from the EPUB NCX/NAV and allow navigation to any chapter.
6. WHEN a User searches for text in an EPUB, THE EPUB_Reader SHALL search across all chapters and highlight matching occurrences.
7. WHEN a User selects text in an EPUB, THE EPUB_Reader SHALL display a context menu with options to highlight, underline, add note, copy, and look up in dictionary.
8. WHEN a User applies a highlight to selected text, THE EPUB_Reader SHALL render the highlight with the chosen color and persist the annotation.
9. WHEN a User adds a bookmark, THE EPUB_Reader SHALL persist the bookmark with chapter reference and reading position.
10. THE EPUB_Reader SHALL remember and restore the last reading position when reopening a Book.

---

### Requirement 4: AZW3 Reader

**User Story:** As a User, I want to read AZW3 (Kindle) books, so that I can access my Kindle library within the same application.

#### Acceptance Criteria

1. WHEN a User opens an AZW3 file, THE AZW3_Reader SHALL convert the file through the pipeline (AZW3 → Calibre parser → internal HTML) and render via QWebEngine.
2. IF the AZW3 conversion fails due to DRM or corruption, THEN THE AZW3_Reader SHALL display a descriptive error message indicating the failure reason.
3. WHILE an AZW3 file is being converted, THE AZW3_Reader SHALL display a progress indicator to the User.
4. WHEN an AZW3 file has been converted, THE AZW3_Reader SHALL cache the converted HTML to avoid re-conversion on subsequent opens.
5. THE AZW3_Reader SHALL provide the same reading features as the EPUB_Reader (highlight, bookmark, search, TOC, font customization, dark mode).

---

### Requirement 5: Annotation System

**User Story:** As a User, I want to annotate my reading materials with highlights, notes, and comments, so that I can capture and organize my thoughts while reading.

#### Acceptance Criteria

1. WHEN a User creates an annotation (highlight, underline, note, or comment), THE Annotation_System SHALL persist the annotation with the exact text position, Book reference, timestamp, and annotation type.
2. THE Annotation_System SHALL support highlight colors: yellow, green, blue, pink, and orange.
3. WHEN a User adds a note to a text selection, THE Annotation_System SHALL store the note content and display a note indicator at the annotation position.
4. WHEN a User adds a comment to an annotation, THE Annotation_System SHALL append the comment with timestamp to the annotation record.
5. WHEN a User tags an annotation, THE Annotation_System SHALL associate the tag with the annotation for filtering and search.
6. WHEN a User opens the annotation panel, THE Annotation_System SHALL display all annotations for the current Book in chronological order, grouped by chapter or page.
7. WHEN a User deletes an annotation, THE Annotation_System SHALL remove the annotation from the database and clear the visual indicator from the rendered content.
8. WHEN a User exports annotations, THE Annotation_System SHALL generate a Markdown file containing all annotations with their context, notes, tags, and source location.

---

### Requirement 6: Dictionary Engine

**User Story:** As a User, I want to look up word definitions instantly while reading, so that I can understand unfamiliar words without leaving the reading context.

#### Acceptance Criteria

1. WHEN a User double-clicks a word in the reader, THE Dictionary_Engine SHALL display a popup with the word definition within 100 milliseconds.
2. THE Dictionary_Engine SHALL follow this lookup order: local cache → local dictionary (StarDict) → online API (configurable: Oxford, Cambridge, Merriam Webster, Wiktionary).
3. WHEN a word is found in local cache, THE Dictionary_Engine SHALL display the cached result without network requests.
4. WHEN a word is not in local cache and network lookup succeeds, THE Dictionary_Engine SHALL cache the result locally for future lookups.
5. IF a word lookup fails from all sources, THEN THE Dictionary_Engine SHALL display a "definition not found" message and offer the User an option to search online.
6. THE Dictionary_Engine SHALL display word definitions including: pronunciation (IPA), part of speech, definitions, example sentences, and synonyms when available.
7. WHEN a User selects a different dictionary source in the popup, THE Dictionary_Engine SHALL fetch and display the definition from the selected source.
8. THE Dictionary_Engine SHALL support multiple languages based on the configured dictionary sources.

---

### Requirement 7: Vocabulary Builder

**User Story:** As a User, I want to save looked-up words to my vocabulary list, so that I can build and review my personal word bank over time.

#### Acceptance Criteria

1. WHEN a User clicks "Save to Vocabulary" in the dictionary popup, THE Vocabulary_Builder SHALL store the word with its definition, pronunciation, example sentence, source Book, and page/position reference.
2. WHEN a word is saved, THE Vocabulary_Builder SHALL assign the word to the default review queue for spaced repetition.
3. WHEN a User opens the Vocabulary panel, THE Vocabulary_Builder SHALL display all saved words sorted by date added, with options to filter by Book, tag, or mastery level.
4. THE Vocabulary_Builder SHALL track mastery levels for each word: New, Learning, Reviewing, Mastered.
5. WHEN a User edits a vocabulary entry, THE Vocabulary_Builder SHALL persist changes to the definition, example, notes, or tags.
6. WHEN a User deletes a vocabulary entry, THE Vocabulary_Builder SHALL remove the word from the vocabulary list and all associated review schedules.
7. WHEN a User exports vocabulary, THE Vocabulary_Builder SHALL generate a CSV or Anki-compatible file containing all vocabulary entries with definitions and examples.

---

### Requirement 8: Spaced Repetition Engine

**User Story:** As a User, I want to review vocabulary using scientifically-proven spaced repetition, so that I can memorize words efficiently and long-term.

#### Acceptance Criteria

1. THE Spaced_Repetition_Engine SHALL implement both SM2 and FSRS scheduling algorithms, with FSRS as the default.
2. WHEN a Review_Session starts, THE Spaced_Repetition_Engine SHALL present due cards in order of priority (overdue first, then due today).
3. WHEN a User rates a card response (Again, Hard, Good, Easy), THE Spaced_Repetition_Engine SHALL calculate the next review interval using the selected algorithm and update the card schedule.
4. THE Spaced_Repetition_Engine SHALL support review modes: flashcard (front/back), multiple choice (4 options), typing (type the answer), and cloze deletion.
5. WHEN a User completes a Review_Session, THE Spaced_Repetition_Engine SHALL display session statistics: cards reviewed, accuracy rate, and time spent.
6. THE Spaced_Repetition_Engine SHALL display daily review statistics on the dashboard: cards due today, cards reviewed, new cards, and review forecast for the next 7 days.
7. WHEN a User switches between SM2 and FSRS algorithms, THE Spaced_Repetition_Engine SHALL recalculate all pending review schedules using the new algorithm.

---

### Requirement 9: Knowledge Graph

**User Story:** As a User, I want to visualize connections between my notes, highlights, and vocabulary, so that I can discover relationships and build deeper understanding.

#### Acceptance Criteria

1. WHEN a User opens the Knowledge Graph view, THE Knowledge_Graph SHALL render a visual graph showing Books, annotations, vocabulary, and tags as connected nodes.
2. WHEN a User creates a backlink between two annotations or notes, THE Knowledge_Graph SHALL store the bidirectional link and display the connection in the graph.
3. WHEN a User clicks a node in the graph, THE Knowledge_Graph SHALL navigate to the corresponding Book, annotation, or vocabulary entry.
4. THE Knowledge_Graph SHALL update the graph visualization within 500 milliseconds when new annotations, vocabulary, or links are created.
5. WHEN a User filters the Knowledge Graph by tag or Book, THE Knowledge_Graph SHALL display only nodes and edges matching the filter criteria.

---

### Requirement 10: Search Engine

**User Story:** As a User, I want to search across all my books, annotations, and vocabulary, so that I can quickly find any piece of information in my library.

#### Acceptance Criteria

1. WHEN a User enters a search query, THE Search_Engine SHALL search across Books (title, author, content), annotations (highlighted text, notes, comments), and vocabulary (word, definition, examples) using SQLite FTS5.
2. THE Search_Engine SHALL return search results within 50 milliseconds for libraries containing up to 10,000 Books.
3. THE Search_Engine SHALL rank results by relevance and display them grouped by category (Books, Annotations, Vocabulary, Notes).
4. WHEN a User clicks a search result, THE Search_Engine SHALL navigate to the exact location of the match in the corresponding Book or panel.
5. THE Search_Engine SHALL support search operators: exact phrase (quotes), AND, OR, and exclude (minus).
6. WHEN the library content changes (new Book imported, annotation added), THE Search_Engine SHALL update the FTS5 index within 1 second.

---

### Requirement 11: Plugin System

**User Story:** As a User, I want to extend the application with plugins, so that I can add custom functionality like additional dictionaries, TTS, or OCR.

#### Acceptance Criteria

1. THE Plugin_System SHALL provide a Python plugin API with defined hooks for: dictionary lookup, text processing, export, import, and UI extension.
2. WHEN a User installs a plugin, THE Plugin_System SHALL validate the plugin structure, load the plugin, and register the plugin hooks.
3. WHEN a User disables a plugin, THE Plugin_System SHALL unregister all hooks and remove the plugin from active processing without deleting plugin data.
4. IF a plugin throws an error during execution, THEN THE Plugin_System SHALL catch the error, log the error details, and continue Application operation without crash.
5. THE Plugin_System SHALL isolate plugin execution so that a faulty plugin cannot corrupt Application data or crash the main process.
6. WHEN a User opens Plugin Settings, THE Plugin_System SHALL display all installed plugins with their status (enabled/disabled), version, and configuration options.

---

### Requirement 12: Application Performance

**User Story:** As a User, I want the application to be fast and responsive, so that I can focus on reading without waiting for the interface.

#### Acceptance Criteria

1. THE Application SHALL complete startup and display the main window within 1 second on a system with SSD storage.
2. THE Dictionary_Engine SHALL display the word lookup popup within 100 milliseconds of a User double-click action.
3. THE PDF_Reader SHALL render visible pages within 16 milliseconds to maintain 60fps during scrolling.
4. THE Search_Engine SHALL return search results within 50 milliseconds.
5. THE Application SHALL consume less than 500 MB of RAM while reading a single Book with the dictionary and annotation panels open.
6. WHEN the User performs a long-running operation (import large library, AZW3 conversion), THE Application SHALL remain responsive and display progress feedback.

---

### Requirement 13: Data Persistence và Integrity

**User Story:** As a User, I want my data (library, annotations, vocabulary, settings) to be safely stored and never lost, so that I can trust the application with my learning progress.

#### Acceptance Criteria

1. THE Application SHALL store all user data (Books metadata, annotations, vocabulary, review schedules, settings, history) in a local SQLite database.
2. WHEN the Application closes, THE Application SHALL save all pending changes to the database before shutdown.
3. IF the Application crashes unexpectedly, THEN THE Application SHALL recover the database to the last consistent state on next startup using SQLite WAL journal.
4. WHEN a User performs a destructive action (delete Book, delete annotation, clear vocabulary), THE Application SHALL request confirmation before executing the action.
5. THE Application SHALL support database backup to a user-specified location on demand.
6. THE Application SHALL migrate the database schema automatically when updating to a new version without data loss.

---

### Requirement 14: User Interface Layout

**User Story:** As a User, I want a clean and intuitive interface layout, so that I can access all features without confusion.

#### Acceptance Criteria

1. THE Application SHALL display a main layout consisting of: Toolbar (top), Navigation Panel (left), Reader Area (center), Side Panel (right), and Status Bar (bottom).
2. WHEN a User toggles the Navigation Panel, THE Application SHALL show or hide the panel with the library browser, Table of Contents, or search results.
3. WHEN a User toggles the Side Panel, THE Application SHALL show or hide the panel with Dictionary, Vocabulary, or Notes tabs.
4. THE Application SHALL persist the panel layout state (open/closed, width) between sessions.
5. WHEN a User resizes a panel, THE Application SHALL respect a minimum panel width of 200 pixels and redistribute remaining space to the Reader Area.
6. THE Application SHALL support keyboard shortcuts for all primary actions (open book, toggle panels, create bookmark, search, navigate pages).
