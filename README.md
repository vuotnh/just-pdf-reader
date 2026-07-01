# AI Ebook Reader & Vocabulary Learning Platform

Ứng dụng đọc sách điện tử tích hợp tra từ điển, ghi chú, hệ thống ôn tập từ vựng (Spaced Repetition), đồ thị tri thức và hỗ trợ plugin mở rộng.

## Yêu cầu hệ thống

- **Python** >= 3.11
- **Calibre** (tùy chọn) — cần thiết nếu muốn đọc file `.azw3` (Kindle). Tải tại: https://calibre-ebook.com
- **Hệ điều hành**: Windows 10+, macOS 12+, hoặc Linux (X11/Wayland)

## Cài đặt

### 1. Clone dự án

```bash
git clone <repository-url>
cd my-book-reader
```

### 2. Tạo virtual environment

```bash
python -m venv .venv
```

Kích hoạt:

- **Windows (CMD):**
  ```cmd
  .venv\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

### 3. Cài đặt dependencies

```bash
pip install -e .
```

Cài thêm dev dependencies (pytest, hypothesis) nếu muốn chạy test:

```bash
pip install -e ".[dev]"
```

## Chạy ứng dụng

```bash
python -m src.main
```

Hoặc sử dụng entry point đã đăng ký:

```bash
ai-ebook-reader
```

## Cấu trúc dự án

```
my-book-reader/
├── src/
│   ├── main.py                    # Entry point
│   ├── application/
│   │   ├── app.py                 # Application lifecycle (startup/shutdown)
│   │   └── services/             # Business logic services
│   ├── domain/
│   │   ├── models.py             # Domain entities (Book, Annotation, VocabularyEntry...)
│   │   ├── enums.py              # Enums (BookFormat, MasteryLevel, Rating...)
│   │   ├── value_objects.py      # Value objects (TextPosition, ReadingPosition...)
│   │   └── algorithms/           # FSRS & SM2 spaced repetition algorithms
│   ├── infrastructure/
│   │   ├── database/             # SQLAlchemy ORM, migrations, FTS5
│   │   ├── readers/              # PDF, EPUB, AZW3 reader backends
│   │   ├── dictionary/           # Dictionary lookup chain & caching
│   │   ├── plugins/              # Plugin loader & hook registry
│   │   ├── repositories/         # Data access layer
│   │   └── parsers/              # Metadata extraction
│   └── presentation/
│       ├── controllers/          # QObject controllers (Python ↔ QML bridge)
│       ├── qml/                  # QML UI views
│       └── shortcuts.py          # Keyboard shortcut registry
├── migrations/                   # Alembic database migrations
├── tests/                        # Unit, property, integration tests
├── resources/                    # Static resources
├── pyproject.toml                # Project configuration & dependencies
└── alembic.ini                   # Alembic configuration
```

## Tính năng chính

| Tính năng | Mô tả |
|-----------|--------|
| **Đọc sách** | Hỗ trợ PDF, EPUB, AZW3 với zoom, tìm kiếm, mục lục |
| **Ghi chú & Highlight** | Highlight, underline, ghi chú với comment threading |
| **Tra từ điển** | Double-click tra từ, hiển thị IPA, định nghĩa, ví dụ |
| **Vocabulary Builder** | Lưu từ vựng, theo dõi mastery level, export CSV/Anki |
| **Spaced Repetition** | Ôn tập với FSRS hoặc SM2, 4 chế độ (flashcard, MCQ, typing, cloze) |
| **Tìm kiếm toàn cục** | FTS5 search across books, annotations, vocabulary |
| **Knowledge Graph** | Đồ thị tri thức liên kết sách, ghi chú, từ vựng |
| **Plugin System** | Mở rộng qua plugin với sandboxed execution |

## Database

Ứng dụng sử dụng SQLite với WAL mode. Database được tạo tự động tại:

- **Windows:** `%APPDATA%/AIEbookReader/ai_ebook_reader.db`
- **macOS:** `~/Library/Application Support/AIEbookReader/ai_ebook_reader.db`
- **Linux:** `~/.local/share/AIEbookReader/ai_ebook_reader.db`

Database migrations chạy tự động khi khởi động ứng dụng.

## AZW3 (Kindle) Support

Để đọc file `.azw3`, cần cài Calibre và đảm bảo `ebook-convert` có trong PATH:

1. Tải và cài Calibre: https://calibre-ebook.com/download
2. Kiểm tra: `ebook-convert --version`

File AZW3 được convert sang HTML và cache tại `~/.ai-ebook-reader/cache/azw3/`.

## Keyboard Shortcuts

| Phím tắt | Hành động |
|----------|-----------|
| `Ctrl+O` | Mở sách |
| `Ctrl+F` | Tìm kiếm |
| `Ctrl+B` | Tạo bookmark |
| `Ctrl+L` | Bật/tắt panel trái |
| `Ctrl+R` | Bật/tắt panel phải |
| `←` / `→` | Chuyển trang |
| `Ctrl++` / `Ctrl+-` | Phóng to / Thu nhỏ |

## Chạy Tests

```bash
# Chạy toàn bộ test
pytest

# Chỉ unit tests
pytest tests/unit/

# Chỉ property-based tests
pytest tests/property/

# Với verbose output
pytest -v
```

## Plugin Development

Plugins được đặt trong thư mục plugins, mỗi plugin gồm:

```
plugins/
└── my-plugin/
    ├── plugin.json    # Metadata: name, version, hooks, permissions
    └── main.py        # Hook implementations
```

**plugin.json** ví dụ:

```json
{
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "A sample plugin",
  "hooks": ["on_word_lookup"],
  "permissions": []
}
```

**Hooks khả dụng:** `on_word_lookup`, `on_text_process`, `on_export`, `on_import`, `on_ui_extend`

**Permissions:** `network`, `file_read`, `file_write`

## License

MIT
