# Hướng dẫn Phát triển Tính năng Mới

## Workflow tổng quát

Khi thêm tính năng mới, follow pattern:

```
1. Domain Layer   → Thêm model/enum nếu cần
2. Infrastructure → Repository / Reader / External API
3. Application    → Service orchestration
4. Presentation   → Controller (QObject) + QML view
```

## Pattern: Thêm tính năng đọc format mới (ví dụ: DJVU)

### Bước 1: Thêm enum

```python
# src/domain/enums.py
class BookFormat(Enum):
    PDF = "pdf"
    EPUB = "epub"
    AZW3 = "azw3"
    DJVU = "djvu"  # ← Thêm
```

### Bước 2: Tạo reader backend

```python
# src/infrastructure/readers/djvu_reader_backend.py
class DJVUReaderBackend:
    def __init__(self, file_path: str = None): ...
    def open(self, file_path: str): ...
    def close(self): ...
    def get_page_count(self) -> int: ...
    def render_page(self, page_num: int, zoom: float) -> bytes: ...  # PNG
    def get_text(self, page_num: int) -> str: ...
    def get_toc(self) -> list: ...
```

### Bước 3: Register trong ReaderFactory

```python
# src/application/services/reader_service.py
_EXTENSION_FORMAT_MAP[".djvu"] = BookFormat.DJVU
```

### Bước 4: Wire vào AppController

```python
# src/presentation/controllers/app_controller.py
def openBook(self, file_path):
    ext = Path(file_path).suffix.lower()
    if ext == ".djvu":
        self._open_djvu(file_path)
```

## Pattern: Thêm context menu action mới

### Bước 1: Thêm HTML menu item

Trong `app_controller.py`, tìm phần `<!-- Context Menu -->`:
```html
<div class="menu-item" data-action="my-action">
    <span class="icon">🎯</span>
    <span class="label">My Action</span>
</div>
```

### Bước 2: Handle trong JS switch

```javascript
case 'my-action':
    console.log('ACTION:my-action:' + selectedText);
    break;
```

### Bước 3: Catch trong QML

```qml
// MainWindow.qml → onJavaScriptConsoleMessage
if (action === "my-action" && appController) {
    appController.myAction(text)
}
```

### Bước 4: Implement slot trong AppController

```python
@Slot(str)
def myAction(self, text: str) -> None:
    # ... logic ...
    pass
```

## Pattern: Thêm service mới

### Template service

```python
# src/application/services/my_service.py
class MyService:
    def __init__(self, some_repo: SomeRepository) -> None:
        self._repo = some_repo
    
    def do_something(self, data: str) -> Result:
        # Business logic here
        return self._repo.save(data)
```

### Template controller

```python
# src/presentation/controllers/my_controller.py
from PySide6.QtCore import QObject, Property, Signal, Slot

class MyController(QObject):
    dataChanged = Signal()
    
    def __init__(self, service: MyService, parent=None):
        super().__init__(parent)
        self._service = service
    
    @Property(str, notify=dataChanged)
    def someData(self) -> str:
        return self._data
    
    @Slot(str)
    def doSomething(self, input: str) -> None:
        result = self._service.do_something(input)
        self._data = result
        self.dataChanged.emit()
```

### Wire vào QML

```qml
// MainWindow.qml hoặc panel riêng
Connections {
    target: myController
    function onDataChanged() {
        // Update UI
    }
}
```

## Pattern: Communication Python ↔ QML (qua WebEngine)

Hiện tại dùng `console.log` bridge:

```
JS → console.log("ACTION:xxx:data")
QML → onJavaScriptConsoleMessage → parse message
QML → appController.someSlot(data)
Python → process → emit signal
QML → Connections { function onSignal() { ... } }
```

Nếu cần 2-way communication phức tạp hơn, dùng **QWebChannel**:
```python
from PySide6.QtWebChannel import QWebChannel
channel = QWebChannel()
channel.registerObject("backend", my_controller)
web_view.page().setWebChannel(channel)
```

## Testing

```bash
# Chạy tất cả tests
pytest

# Test một module cụ thể
pytest tests/unit/test_pdf_text_layer.py -v

# Test với output
pytest -s --log-cli-level=DEBUG
```

## Quy ước code

- **Python:** PEP 8, type hints, docstrings
- **QML:** Camel case properties/signals, snake_case JS functions
- **Commits:** Conventional commits (feat:, fix:, refactor:)
- **Files:** Snake case cho Python, PascalCase cho QML
