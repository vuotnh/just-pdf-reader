# Hướng dẫn Debug & Troubleshooting

## Log Files

Ứng dụng ghi log ra cả terminal và file:

```
~/.ai-ebook-reader/logs/app.log
```

Log level: DEBUG (ghi tất cả). Format:
```
2024-01-01 12:00:00 [INFO] module.name: message
```

## Các vấn đề thường gặp

### 1. Mở app không hiện cửa sổ

**Nguyên nhân:** QML load lỗi.

**Debug:**
```bash
python -m src.main
```
Xem terminal có lỗi QML nào không (file not found, syntax error).

**Fix:** Kiểm tra file `src/presentation/qml/MainWindow.qml` tồn tại và syntax đúng.

### 2. PDF mở nhưng trắng (không hiện nội dung)

**Nguyên nhân:** HTML quá lớn hoặc render lỗi.

**Debug:**
1. Thêm `print(len(self._page_html))` trong `_update_page_html`
2. Nếu > 5MB → giảm render scale
3. Check terminal cho PyMuPDF errors

**Fix:** Trong `app_controller.py`, giảm `render_scale = zoom * 2` xuống `zoom * 1.5`.

### 3. Text selection bị lệch

**Nguyên nhân:** Text layer spans không khớp vị trí image.

**Debug:**
1. Mở DevTools trong WebEngineView (thêm `settings.developerExtrasEnabled: true` vào QML)
2. Inspect `.text-layer span` elements
3. So sánh CSS `left/top` với vị trí text trên image

**Fix:** File `src/infrastructure/readers/pdf_text_layer.py`:
- Kiểm tra `chars[0]["bbox"]` có đúng toạ độ không
- Đảm bảo zoom multiplier consistent giữa image render và text positioning

### 4. Dictionary lookup timeout / not found

**Nguyên nhân:** Network bị chặn (corporate firewall).

**Debug:**
```python
python -c "import requests; r=requests.get('https://dictionary.cambridge.org', timeout=5); print(r.status_code)"
```

**Fix:** App đã fallback sang embed WebEngineView load Cambridge trực tiếp (dùng system network). Nếu WebView cũng không load → mạng chặn hoàn toàn.

### 5. Highlights mất sau khi đóng/mở

**Debug:**
1. Check file: `~/.ai-ebook-reader/highlights/` có file JSON không
2. In ra `_file_hash(self._file_path)` xem hash có consistent không
3. Check log: `"Saved X highlights for..."`

**Fix:** Đảm bảo `self._file_path` được set đúng trong `_open_pdf()`.

### 6. Context menu hiện sai vị trí / bị broken

**Nguyên nhân:** HTML structure lỗi (thẻ không đóng, duplicate).

**Debug:**
1. Save `self._page_html` ra file: `Path("/tmp/debug.html").write_text(self._page_html)`
2. Mở trong Chrome → Inspect HTML structure
3. Check `.context-menu` element có đủ items không

### 7. Application startup failed

**Nguyên nhân:** Database migration lỗi hoặc file bị corrupt.

**Debug:** Check log cho:
```
Database integrity issues found: [...]
```

**Fix:** Xoá database file rồi restart:
```bash
del %USERPROFILE%\.ai-ebook-reader\data\library.db
```

## Debug Tools

### Enable WebEngine DevTools

Trong `MainWindow.qml`, thêm vào WebEngineView:
```qml
settings.developerExtrasEnabled: true
```
Sau đó right-click → "Inspect Element" để mở DevTools.

### Test từng component

```python
# Test PDF render
import fitz
doc = fitz.open("path/to/pdf")
page = doc[0]
pix = page.get_pixmap(matrix=fitz.Matrix(2,2))
pix.save("test_page.png")

# Test text layer
from src.infrastructure.readers.pdf_text_layer import extract_word_spans
spans = extract_word_spans(page)
for s in spans[:10]:
    print(f"[{s.text}] at ({s.left:.1f}, {s.top:.1f}) w={s.width:.1f}")

# Test highlight store
from src.infrastructure.readers.pdf_highlights_store import *
hl = add_highlight("test.pdf", 0, "yellow", "hello world")
print(load_highlights("test.pdf"))

# Test Cambridge parser (needs network)
from src.infrastructure.dictionary.cambridge_parser import lookup_cambridge
result = lookup_cambridge("hello")
print(result.to_dict() if result else "Not found")
```

### Profile performance

```python
import time
start = time.perf_counter()
# ... code to profile ...
print(f"Took {(time.perf_counter()-start)*1000:.1f}ms")
```

Bottleneck thường là:
- `page.get_pixmap()` — 50-200ms per page
- `base64.b64encode()` — 10-50ms
- `generate_text_layer_html()` — 20-100ms (depends on text density)

## Log Messages Reference

| Log Pattern | Meaning |
|---|---|
| `Application startup initiated` | App đang khởi động |
| `Database engine created: ...` | SQLite connection OK |
| `Database integrity check passed` | DB không bị corrupt |
| `WAL checkpoint completed` | Crash recovery done |
| `Opened PDF: ... (N pages)` | PDF load thành công |
| `Dictionary lookup for 'X'` | User tra từ |
| `Highlight saved: page=N` | Highlight được lưu |
| `[DICT] Lookup 'X'` | Console log khi tra từ |
| `NAV:next` / `NAV:prev` | Scroll chuyển trang |
