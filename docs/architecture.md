# Kiến trúc ứng dụng AI Ebook Reader

## Tổng quan

AI Ebook Reader là ứng dụng desktop đọc sách điện tử được xây dựng với Python + PySide6 (Qt6). Ứng dụng theo kiến trúc **Clean Architecture** với 4 layer chính:

```
┌─────────────────────────────────────────────────────┐
│                  Presentation Layer                   │
│         (QML Views + Python Controllers)             │
├─────────────────────────────────────────────────────┤
│                  Application Layer                    │
│              (Services + App Lifecycle)               │
├─────────────────────────────────────────────────────┤
│                    Domain Layer                       │
│          (Models + Enums + Algorithms)               │
├─────────────────────────────────────────────────────┤
│                Infrastructure Layer                   │
│   (Database + Readers + Dictionary + Plugins)        │
└─────────────────────────────────────────────────────┘
```

## Cấu trúc thư mục

```
src/
├── main.py                          # Entry point
├── application/
│   ├── app.py                       # Application lifecycle (startup/shutdown)
│   └── services/
│       ├── library_service.py       # Quản lý thư viện sách
│       ├── annotation_service.py    # Quản lý ghi chú, highlight
│       ├── dictionary_service.py    # Tra từ điển
│       ├── vocabulary_service.py    # Quản lý từ vựng
│       ├── spaced_repetition_service.py  # Hệ thống ôn tập
│       ├── search_service.py        # Tìm kiếm FTS5
│       ├── knowledge_graph_service.py   # Đồ thị tri thức
│       ├── plugin_service.py        # Quản lý plugin
│       └── reader_service.py        # Orchestration mở sách
├── domain/
│   ├── models.py                    # Domain entities (dataclass)
│   ├── enums.py                     # BookFormat, MasteryLevel, Rating...
│   ├── value_objects.py             # TextPosition, ReadingPosition...
│   └── algorithms/
│       ├── base.py                  # ISchedulingAlgorithm protocol
│       ├── fsrs.py                  # FSRS-4.5 algorithm
│       └── sm2.py                   # SuperMemo 2 algorithm
├── infrastructure/
│   ├── database/
│   │   ├── engine.py                # SQLAlchemy engine + WAL mode
│   │   ├── session.py               # Session factory
│   │   ├── models.py                # ORM models (SQLAlchemy)
│   │   ├── fts.py                   # FTS5 virtual tables + triggers
│   │   └── migrations.py           # Alembic auto-migration
│   ├── readers/
│   │   ├── pdf_reader_backend.py    # PyMuPDF PDF rendering
│   │   ├── pdf_text_layer.py        # Text overlay generation (per-char bbox)
│   │   ├── pdf_highlights_store.py  # Highlight persistence (JSON)
│   │   ├── epub_reader_backend.py   # EPUB parsing + WebEngine
│   │   └── azw3_reader_backend.py   # AZW3 → HTML via Calibre
│   ├── dictionary/
│   │   ├── cambridge_parser.py      # Cambridge Dictionary scraper
│   │   ├── lookup_chain.py          # Chain of responsibility lookup
│   │   ├── dict_cache.py            # SQLite cache
│   │   ├── stardict_reader.py       # Local StarDict format
│   │   └── online_api.py           # Online API clients
│   ├── plugins/
│   │   ├── plugin_loader.py         # Discovery + sandbox loading
│   │   └── hook_registry.py         # Event dispatch system
│   ├── repositories/
│   │   ├── book_repository.py       # Book CRUD
│   │   ├── annotation_repository.py # Annotation CRUD
│   │   ├── vocabulary_repository.py # Vocab + ReviewCard CRUD
│   │   └── knowledge_repository.py  # KnowledgeNode/Link CRUD
│   └── parsers/
│       └── metadata_extractor.py    # PDF/EPUB metadata extraction
└── presentation/
    ├── shortcuts.py                 # Keyboard shortcut registry
    ├── controllers/
    │   ├── app_controller.py        # Main controller (PDF render + dict)
    │   ├── library_controller.py    # Library QML bridge
    │   ├── annotation_controller.py # Annotation QML bridge
    │   ├── dictionary_controller.py # Dictionary popup bridge
    │   ├── vocabulary_controller.py # Vocabulary panel bridge
    │   ├── review_controller.py     # Spaced repetition bridge
    │   ├── search_controller.py     # Search panel bridge
    │   ├── knowledge_graph_controller.py  # Graph viz bridge
    │   └── plugin_controller.py     # Plugin settings bridge
    └── qml/
        ├── MainWindow.qml           # Main layout (toolbar + panels)
        ├── Toolbar.qml              # Top toolbar
        ├── StatusBar.qml            # Bottom status bar
        └── ... (other views)
```

## Technology Stack

| Component | Technology | Lý do chọn |
|-----------|-----------|-------------|
| Language | Python 3.11+ | Ecosystem phong phú, rapid development |
| GUI Framework | PySide6 (Qt6) | Cross-platform, native look, QML + WebEngine |
| PDF Rendering | PyMuPDF (fitz) | Nhanh, chính xác, per-char bbox |
| Web Rendering | QWebEngineView | Native text selection, HTML/CSS rendering |
| Database | SQLite + SQLAlchemy | Embedded, WAL mode, FTS5 |
| Migrations | Alembic | Auto schema evolution |
| Build | PyInstaller | Single exe packaging |

## Data Flow

### Mở file PDF

```
User click 📂 → QML FileDialog
    → onAccepted: filePath
    → appController.openBook(filePath)
        → fitz.open(filePath)
        → Extract TOC → emit tocChanged
        → _update_page_html()
            → page.get_pixmap() → PNG base64
            → generate_text_layer_html(page, zoom)
            → Load saved highlights from JSON
            → Build HTML (image bg + text overlay + context menu + JS)
            → emit pageHtmlChanged
    → QML onPageHtmlChanged
        → pdfWebView.loadHtml(html)
        → User sees rendered page with selectable text
```

### Text Selection + Highlight

```
User drags mouse → Browser native selection (transparent text layer)
    → Right click → JS contextmenu event
        → Show custom context menu
        → User clicks "Highlight Yellow"
            → JS: extractContents() + wrap in <mark>
            → JS: console.log('SAVE_HIGHLIGHT:yellow:selected text')
    → QML onJavaScriptConsoleMessage
        → Parse "SAVE_HIGHLIGHT:color:text"
        → appController.saveHighlight(color, text)
            → add_highlight() → write JSON file
    
When page re-renders:
    → get_page_highlights() → load from JSON
    → JS on load: apply 'hl-saved-{color}' class to matching spans
```

### Dictionary Lookup

```
User selects text → Right click → "Look Up Dictionary"
    → JS: console.log('ACTION:dictionary:word')
    → QML catches message
        → appController.lookupDictionary(word)
            → Build Cambridge URLs
            → emit dictionaryResultReady(json)
    → QML onDictionaryResultReady
        → Parse JSON with URLs
        → dictWebView.url = cambridge_url
        → Show dictionary popup panel
```

### Page Navigation

```
Scroll wheel at bottom of page:
    → JS: console.log('NAV:next')
    → QML: appController.nextPage()
        → _current_page += 1
        → _update_page_html()  // re-render new page

Toolbar ◀ ▶ buttons:
    → QML: appController.previousPage() / nextPage()

TOC click:
    → QML: appController.goToPage(pageNum)

Keyboard Left/Right:
    → QML Shortcut → appController.previousPage() / nextPage()
```

### Zoom

```
Toolbar +/- or Ctrl+Scroll:
    → appController.zoomIn() / zoomOut()
        → self._zoom += 0.25
        → _update_page_html()  // re-render at new zoom
            → fitz.Matrix(zoom * 2, zoom * 2) for crisp image
            → Text layer positions × zoom
            → Same page, different scale
```

## Database Schema

SQLite database tại `~/.ai-ebook-reader/data/library.db`:

- **books** — Metadata sách (title, author, path, format, hash)
- **annotations** — Highlights, notes, bookmarks
- **vocabulary_entries** — Từ vựng đã lưu
- **review_cards** — Flashcard cho spaced repetition
- **review_logs** — Lịch sử ôn tập
- **knowledge_nodes** — Nodes trong đồ thị tri thức
- **knowledge_links** — Edges giữa nodes
- **tags** — Tags hệ thống
- **collections** — Bộ sưu tập sách
- **books_fts / annotations_fts / vocabulary_fts** — FTS5 virtual tables

## Highlights Storage

Highlights được lưu dưới dạng JSON file:
- Location: `~/.ai-ebook-reader/highlights/<hash>.json`
- Hash = SHA256(file_path)[:16]
- Mỗi file chứa array highlights với: page, color, text, created_at

## Plugin System

Plugins nằm trong thư mục `plugins/`:
```
plugins/
└── my-plugin/
    ├── plugin.json     # Metadata
    └── main.py         # Hook implementations
```

**Sandbox restrictions:**
- Không có `eval`, `exec`, `compile`, `__import__` (trừ whitelist)
- File I/O chỉ trong thư mục plugin
- Network chỉ khi khai báo permission
- Timeout 5 giây per hook call

**Available hooks:**
- `on_word_lookup` — Bổ sung kết quả tra từ
- `on_text_process` — Xử lý text (TTS, dịch)
- `on_export` — Custom export format
- `on_import` — Custom import format
- `on_ui_extend` — Mở rộng UI

## Keyboard Shortcuts

Defined in `src/presentation/shortcuts.py`:
- Ctrl+O: Open book
- Ctrl+F: Search
- Ctrl+B: Bookmark
- Ctrl+L/R: Toggle panels
- Left/Right: Navigate pages
- Ctrl++/-: Zoom
- Ctrl+Z: Undo highlight
