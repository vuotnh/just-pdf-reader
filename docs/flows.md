# Chi tiết Luồng Hoạt động

## 1. Luồng khởi động ứng dụng

```
main.py
│
├─ os.environ["QT_QUICK_CONTROLS_STYLE"] = "Fusion"
├─ QtWebEngineQuick.initialize()     ← BẮT BUỘC trước QApplication
├─ QApplication(sys.argv)
│
├─ Application()                     ← src/application/app.py
│   └─ startup()
│       ├─ create_db_engine()        ← SQLite WAL mode + pragmas
│       ├─ _perform_crash_recovery() ← PRAGMA integrity_check + checkpoint
│       ├─ check_and_run_migrations()← Alembic upgrade head
│       ├─ SessionFactory(engine)
│       └─ _load_settings()         ← QSettings
│
├─ AppController()                   ← Main Python↔QML bridge
├─ QQmlApplicationEngine()
│   ├─ rootContext.setContextProperty("appController", ...)
│   └─ engine.load("MainWindow.qml")
│
└─ app.exec()                        ← Qt event loop starts
```

## 2. Luồng mở file PDF

```
[User] Click 📂 hoặc Ctrl+O
    │
    ▼
[QML] FileDialog opens
    │ User chọn file .pdf
    ▼
[QML] openFileDialog.onAccepted
    │ filePath = selectedFile (remove file:/// prefix)
    ▼
[QML] appController.openBook(filePath)
    │
    ▼
[Python] AppController.openBook()
    ├─ Detect extension → ".pdf"
    └─ _open_pdf(file_path)
        ├─ fitz.open(file_path)          ← PyMuPDF
        ├─ page_count = doc.page_count
        ├─ doc.get_toc() → toc_json      ← Extract TOC
        ├─ emit bookOpened, tocChanged, zoomChanged
        └─ _update_page_html()
            │
            ▼
[Python] _update_page_html()
    ├─ page = doc[current_page]
    ├─ fitz.Matrix(zoom * 2, zoom * 2)   ← 2x for HiDPI crisp
    ├─ page.get_pixmap(matrix=mat)       ← Render to pixels
    ├─ base64.b64encode(png_bytes)       ← Encode for HTML embed
    ├─ generate_text_layer_html(page, zoom)  ← Per-char bbox spans
    ├─ get_page_highlights(file_path, page)  ← Load saved highlights
    ├─ Build HTML string:
    │   ├─ <img> with base64 PNG (background)
    │   ├─ .text-layer with transparent <span>s (selectable)
    │   ├─ .context-menu div (right-click menu)
    │   ├─ <script> for scaleX + scroll nav + context menu logic
    │   └─ Saved highlights JSON for JS to apply
    └─ emit pageHtmlChanged
        │
        ▼
[QML] Connections.onPageHtmlChanged()
    └─ pdfWebView.loadHtml(html, "about:blank")
        │
        ▼
[WebEngine] Renders HTML
    ├─ Shows crisp PDF image
    ├─ Transparent text layer on top (selectable)
    ├─ JS runs: scaleX each span to match bbox width
    └─ JS runs: apply saved highlights to matching spans
```

## 3. Luồng Text Selection + Highlight

```
[User] Drags mouse over text
    │
    ▼
[WebEngine] Browser native selection on .text-layer spans
    │ Text appears highlighted blue (::selection CSS)
    │
    ▼
[User] Right-click
    │
    ▼
[JS] contextmenu event handler
    ├─ e.preventDefault()             ← Block default browser menu
    ├─ window.getSelection().toString()
    ├─ selectedText = "some words"
    ├─ selectionRange = sel.getRangeAt(0)
    └─ Show .context-menu at (clientX, clientY)
        │
        ▼
[User] Clicks "🟡 Highlight Yellow"
    │
    ▼
[JS] contextMenu click handler
    ├─ action = "highlight-yellow" → color = "yellow"
    └─ applyHighlight("yellow")
        ├─ document.createElement('mark')
        ├─ mark.className = 'hl hl-yellow'
        ├─ range.extractContents() → fragment
        ├─ mark.appendChild(fragment)
        ├─ range.insertNode(mark)         ← Visual highlight applied
        ├─ console.log('ACTION:highlight-yellow:text')
        └─ console.log('SAVE_HIGHLIGHT:yellow:text')
            │
            ▼
[QML] onJavaScriptConsoleMessage
    ├─ Parse "SAVE_HIGHLIGHT:yellow:text"
    └─ appController.saveHighlight("yellow", "text")
        │
        ▼
[Python] saveHighlight()
    └─ add_highlight(file_path, current_page, color, text)
        ├─ Load existing JSON
        ├─ Append new highlight
        └─ Write JSON to ~/.ai-ebook-reader/highlights/<hash>.json
```

## 4. Luồng Dictionary Lookup

```
[User] Select text → Right-click → "📖 Look Up Dictionary"
    │
    ▼
[JS] console.log('ACTION:dictionary:reactive')
    │
    ▼
[QML] onJavaScriptConsoleMessage
    ├─ Parse "ACTION:dictionary:reactive"
    └─ appController.lookupDictionary("reactive")
        │
        ▼
[Python] lookupDictionary("reactive")
    ├─ Build Cambridge URLs:
    │   ├─ EN-VI: cambridge.org/dictionary/english-vietnamese/reactive
    │   └─ EN-EN: cambridge.org/dictionary/english/reactive
    ├─ Create JSON: {word, urls, mode: "webview"}
    ├─ print("[DICT] Lookup 'reactive'")   ← Terminal log
    └─ emit dictionaryResultReady(json)
        │
        ▼
[QML] Connections.onDictionaryResultReady(jsonStr)
    ├─ Parse JSON
    ├─ dictHeaderLabel.text = word
    ├─ dictWebView.url = urls.en_vi       ← Load Cambridge page
    ├─ dictPopup.visible = true
    └─ User sees Cambridge dictionary in side panel
```

## 5. Luồng Page Navigation (Scroll)

```
[User] Scrolls mouse wheel at bottom of page
    │
    ▼
[JS] wheel event handler
    ├─ Check: atBottom = (scrollY + innerHeight >= body.scrollHeight - 5)
    ├─ e.deltaY > 0 && atBottom → true
    └─ console.log('NAV:next')
        │
        ▼
[QML] onJavaScriptConsoleMessage
    ├─ message === "NAV:next"
    └─ appController.nextPage()
        │
        ▼
[Python] nextPage()
    └─ goToPage(current_page + 1)
        ├─ _current_page = new_page
        ├─ _update_page_html()  ← Re-render next page
        └─ emit pageChanged
            │
            ▼
[QML] Status bar updates: "Page X / Y"
[QML] TOC highlight updates
```

## 6. Luồng Zoom

```
[User] Click "+" toolbar / Ctrl+= / Ctrl+scroll
    │
    ▼
[QML or Python] appController.zoomIn()
    │
    ▼
[Python] setZoom(zoom + 0.25)
    ├─ self._zoom = new_zoom (clamped 0.5 - 4.0)
    ├─ _update_page_html()
    │   ├─ fitz.Matrix(new_zoom * 2, new_zoom * 2)  ← Larger image
    │   ├─ text spans × new_zoom                      ← Larger positions
    │   └─ Same page, new scale
    └─ emit zoomChanged
        │
        ▼
[QML] Toolbar label updates: "150%"
[WebEngine] Re-renders page at new zoom (crisp at any level)
```

## 7. Luồng TOC Navigation

```
[User] Clicks TOC entry "Chapter 3" (page 45)
    │
    ▼
[QML] tocListView delegate.onClicked
    └─ appController.goToPage(45)
        │
        ▼
[Python] goToPage(45)
    ├─ _current_page = 45
    ├─ _update_page_html()  ← Render page 45
    └─ emit pageChanged
        │
        ▼
[QML] Status bar: "Page 46 / 521"
[QML] TOC: highlight "Chapter 3" with blue bg
```

## 8. Luồng Application Shutdown

```
[User] Closes window
    │
    ▼
[Qt] app.aboutToQuit signal
    │
    ▼
[Python] Application.shutdown()
    ├─ _flush_pending_changes()
    │   └─ PRAGMA wal_checkpoint(FULL)
    ├─ _save_layout_state()
    │   └─ QSettings.sync()
    └─ _close_database()
        └─ engine.dispose()
```

## Diagram: Component Interaction

```
┌──────────┐     ┌──────────────┐     ┌────────────────┐
│   QML    │────▶│ AppController│────▶│ PyMuPDF (fitz) │
│ MainWin  │◀────│  (QObject)   │◀────│  PDF Backend   │
└──────────┘     └──────────────┘     └────────────────┘
     │                  │                      │
     │ loadHtml         │ signals              │ get_pixmap
     ▼                  ▼                      │ get_text
┌──────────┐     ┌──────────────┐             │ rawdict
│WebEngine │     │  Highlight   │             ▼
│  View    │     │    Store     │     ┌────────────────┐
│(renders  │     │  (JSON fs)   │     │ pdf_text_layer │
│ HTML)    │     └──────────────┘     │ (per-char bbox)│
└──────────┘                          └────────────────┘
```
