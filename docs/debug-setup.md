# Setup Debug Environment

## IDE Setup (VS Code)

### 1. Cài extensions

- **Python** (Microsoft)
- **QML** (Qt Group) — syntax highlighting cho .qml files
- **Pylance** — type checking

### 2. launch.json

Tạo `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run App",
            "type": "debugpy",
            "request": "launch",
            "module": "src.main",
            "cwd": "${workspaceFolder}",
            "env": {
                "QT_QUICK_CONTROLS_STYLE": "Fusion",
                "QTWEBENGINE_REMOTE_DEBUGGING": "9222"
            },
            "justMyCode": false
        },
        {
            "name": "Run App (Console)",
            "type": "debugpy",
            "request": "launch",
            "module": "src.main",
            "cwd": "${workspaceFolder}",
            "console": "integratedTerminal",
            "env": {
                "QT_QUICK_CONTROLS_STYLE": "Fusion"
            }
        },
        {
            "name": "Run Tests",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["tests/", "-v", "--tb=short"],
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Test Single Module",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["${file}", "-v"],
            "cwd": "${workspaceFolder}"
        }
    ]
}
```

### 3. settings.json

```json
{
    "python.defaultInterpreterPath": ".venv/Scripts/python.exe",
    "python.analysis.typeCheckingMode": "basic",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"],
    "files.associations": {
        "*.qml": "qml"
    }
}
```

## Debug Techniques

### Breakpoints trong Python

Đặt breakpoint bình thường trong VS Code. Các vị trí hữu ích:

```
src/main.py:42                     ← Ngay trước startup()
src/application/app.py:96          ← Đầu startup()
src/presentation/controllers/app_controller.py:220  ← openBook()
src/presentation/controllers/app_controller.py:250  ← _update_page_html()
src/infrastructure/readers/pdf_text_layer.py:80     ← extract_word_spans()
```

### Debug WebEngine (HTML/JS)

**Cách 1: Remote DevTools**

Thêm environment variable trước khi chạy:
```bash
set QTWEBENGINE_REMOTE_DEBUGGING=9222
python -m src.main
```

Sau đó mở Chrome → `http://localhost:9222` → chọn page → Full DevTools.

**Cách 2: Console log**

Tất cả `console.log()` trong JS được forward tới QML `onJavaScriptConsoleMessage`.
Output hiện trong terminal. Thêm log:

```javascript
// Trong HTML template (app_controller.py)
console.log('DEBUG: selection =', window.getSelection().toString());
console.log('DEBUG: span count =', document.querySelectorAll('.text-layer span').length);
```

**Cách 3: Inspect HTML output**

Thêm code tạm vào `_update_page_html()`:
```python
# Save HTML to file for inspection
Path("debug_page.html").write_text(html, encoding="utf-8")
```
Mở `debug_page.html` trong Chrome để inspect DOM, CSS, behavior.

### Debug QML

**Cách 1: console.log trong QML**
```qml
onClicked: {
    console.log("Button clicked, appController:", appController)
    console.log("isBookOpen:", appController.isBookOpen)
}
```

**Cách 2: QML Debug Server**
```bash
set QML_IMPORT_TRACE=1
set QT_LOGGING_RULES=qt.qml.binding=true
python -m src.main
```

**Cách 3: Gammaray (Qt inspector)**
Download từ https://www.kdab.com/development-resources/qt-tools/gammaray/
Attach vào running process → inspect QML tree, signals, properties.

### Debug Database

```python
# Interactive SQLite
python -c "
import sqlite3
conn = sqlite3.connect(r'C:\Users\<user>\.ai-ebook-reader\data\library.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
print(cursor.fetchall())
conn.close()
"
```

Hoặc dùng **DB Browser for SQLite**: https://sqlitebrowser.org/

### Debug PDF Rendering

```python
# Test render a specific page
import fitz
doc = fitz.open("path/to/file.pdf")
page = doc[5]  # page 6

# Check page dimensions
print(f"Page size: {page.rect}")  # e.g. Rect(0, 0, 612, 792)

# Render to PNG
pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
pix.save("debug_page5.png")

# Check text extraction
text_dict = page.get_text("rawdict")
for block in text_dict["blocks"][:2]:
    if block["type"] == 0:
        for line in block["lines"]:
            for span in line["spans"]:
                chars = span.get("chars", [])
                print(f"Text: '{span['text']}' bbox: {span['bbox']}")
                if chars:
                    print(f"  First char: {chars[0]}")
```

### Debug Highlights Store

```python
from src.infrastructure.readers.pdf_highlights_store import *

# List all highlights for a file
file_path = "C:/path/to/my/book.pdf"
highlights = load_highlights(file_path)
for h in highlights:
    print(f"Page {h.page}: [{h.color}] '{h.text[:50]}...'")

# Check store path
print(f"Store: {_store_path(file_path)}")
```

## Common Debug Scenarios

### "Page hiện trắng"

1. Check terminal output — lỗi Python?
2. Check `len(self._page_html)` — quá lớn (>10MB)?
3. Save HTML ra file → mở Chrome → xem render được không?
4. Check `pageHtmlChanged` signal có emit không?
5. Check QML `pdfWebView.loadHtml()` có được gọi không?

### "Text selection lệch"

1. Save HTML → mở Chrome → DevTools → inspect `.text-layer span`
2. Check span `left/top` CSS vs text position trên image
3. Test: `from src.infrastructure.readers.pdf_text_layer import extract_word_spans`
4. Compare `span.left * zoom` vs actual pixel position

### "Signal không emit / QML không nhận"

1. Check signal name: Python `camelCase` ↔ QML `onCamelCase`
2. Check Connections target đúng object
3. Thêm `console.log()` trong QML handler
4. Thêm `print()` trước emit trong Python

### "App crash không có log"

Chạy với console để thấy traceback:
```bash
python -m src.main
```

Nếu crash trong C++ (Qt/WebEngine), enable core dump:
```bash
set QT_FATAL_WARNINGS=1
python -m src.main
```

## Performance Profiling

```python
import cProfile
import pstats

# Profile startup
cProfile.run('main()', 'startup.prof')
stats = pstats.Stats('startup.prof')
stats.sort_stats('cumulative')
stats.print_stats(20)
```

Or per-function timing:
```python
import time

class Timer:
    def __init__(self, label):
        self.label = label
    def __enter__(self):
        self.start = time.perf_counter()
    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self.start) * 1000
        print(f"[PERF] {self.label}: {elapsed:.1f}ms")

# Usage
with Timer("render page"):
    pix = page.get_pixmap(matrix=mat)
with Timer("base64 encode"):
    b64 = base64.b64encode(png).decode()
with Timer("text layer"):
    html = generate_text_layer_html(page, zoom)
```

Typical timing (per page, zoom=1.0):
- `get_pixmap()`: 50-150ms
- `base64.b64encode()`: 10-30ms
- `generate_text_layer_html()`: 20-80ms
- Total page render: 100-300ms

## Environment Variables

| Variable | Effect |
|----------|--------|
| `QT_QUICK_CONTROLS_STYLE=Fusion` | Qt style (required) |
| `QTWEBENGINE_REMOTE_DEBUGGING=9222` | Enable Chrome DevTools |
| `QML_IMPORT_TRACE=1` | Log QML imports |
| `QT_LOGGING_RULES=qt.qml.*=true` | Verbose QML logging |
| `QT_FATAL_WARNINGS=1` | Crash on Qt warnings |
| `PYTHONTRACEMALLOC=1` | Memory tracking |
