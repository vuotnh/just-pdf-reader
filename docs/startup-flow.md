# Luồng Khởi động Ứng dụng (Chi tiết)

## Sequence Diagram

```
┌─────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌───────────┐
│  main.py │    │Application│    │   Database   │    │QML Engine│    │ MainWindow│
└────┬─────┘    └─────┬─────┘    └──────┬───────┘    └─────┬─────┘    └─────┬─────┘
     │                │                  │                  │                │
     │ 1. Set env vars│                  │                  │                │
     │────────────────│                  │                  │                │
     │                │                  │                  │                │
     │ 2. QtWebEngineQuick.initialize() │                  │                │
     │────────────────│                  │                  │                │
     │                │                  │                  │                │
     │ 3. QApplication()                 │                  │                │
     │────────────────│                  │                  │                │
     │                │                  │                  │                │
     │ 4. Application()                  │                  │                │
     │───────────────▶│                  │                  │                │
     │                │                  │                  │                │
     │ 5. startup()   │                  │                  │                │
     │───────────────▶│                  │                  │                │
     │                │ 5a. create_engine│                  │                │
     │                │─────────────────▶│                  │                │
     │                │                  │ SQLite WAL mode  │                │
     │                │◀─────────────────│                  │                │
     │                │                  │                  │                │
     │                │ 5b. integrity_check                 │                │
     │                │─────────────────▶│                  │                │
     │                │                  │ PRAGMA result    │                │
     │                │◀─────────────────│                  │                │
     │                │                  │                  │                │
     │                │ 5c. WAL checkpoint                  │                │
     │                │─────────────────▶│                  │                │
     │                │◀─────────────────│                  │                │
     │                │                  │                  │                │
     │                │ 5d. run_migrations                  │                │
     │                │─────────────────▶│                  │                │
     │                │                  │ Alembic upgrade  │                │
     │                │◀─────────────────│                  │                │
     │                │                  │                  │                │
     │   True         │                  │                  │                │
     │◀───────────────│                  │                  │                │
     │                │                  │                  │                │
     │ 6. AppController()                │                  │                │
     │────────────────│                  │                  │                │
     │                │                  │                  │                │
     │ 7. QQmlApplicationEngine()        │                  │                │
     │───────────────────────────────────────────────────▶│                │
     │                │                  │                  │                │
     │ 8. setContextProperty("appController")              │                │
     │───────────────────────────────────────────────────▶│                │
     │                │                  │                  │                │
     │ 9. engine.load("MainWindow.qml")  │                  │                │
     │───────────────────────────────────────────────────▶│                │
     │                │                  │                  │  create window │
     │                │                  │                  │───────────────▶│
     │                │                  │                  │                │
     │ 10. app.exec() ← Qt Event Loop                      │                │
     │════════════════════════════════════════════════════════════════════════│
```

## Code walkthrough: `src/main.py`

```python
# ─── STEP 1: Environment Setup ───
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
# WHY: Fusion style supports CSS customization. Native style doesn't.
# WHAT HAPPENS IF MISSING: ProgressBar/buttons won't render correctly

# ─── STEP 2: WebEngine Init ───
from PySide6.QtWebEngineQuick import QtWebEngineQuick
QtWebEngineQuick.initialize()
# WHY: MUST be called BEFORE QApplication. Qt6 requirement.
# WHAT HAPPENS IF MISSING: WebEngineView won't load, app crashes

# ─── STEP 3: QApplication ───
app = QApplication(sys.argv)
# WHY: Required for any Qt GUI app. Creates event loop.

# ─── STEP 4-5: Application Lifecycle ───
application = Application()
application.startup()
# WHAT startup() DOES:
#   1. create_db_engine() → SQLite at ~/.ai-ebook-reader/data/library.db
#      - Sets WAL mode, foreign keys, synchronous=NORMAL
#   2. _perform_crash_recovery()
#      - PRAGMA integrity_check → verify DB not corrupt
#      - PRAGMA wal_checkpoint(TRUNCATE) → consolidate WAL
#   3. check_and_run_migrations()
#      - Alembic: checks current revision vs head
#      - Runs any pending migrations
#   4. SessionFactory(engine) → ready for DB queries
#   5. QSettings load → panel sizes, window geometry

# ─── STEP 6: AppController ───
app_controller = AppController()
# This is the MAIN bridge between Python and QML.
# It handles: PDF rendering, page navigation, zoom, dict lookup, highlights

# ─── STEP 7-9: QML Loading ───
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("appController", app_controller)
engine.load(qml_path)
# QML file parsed → creates ApplicationWindow → displays UI

# ─── STEP 10: Event Loop ───
return app.exec()
# Blocks here until window is closed. All user interaction happens via
# Qt signals/slots in this event loop.
```

## File Paths

| Data | Location | Created by |
|------|----------|-----------|
| Database | `~/.ai-ebook-reader/data/library.db` | engine.py |
| Logs | `~/.ai-ebook-reader/logs/app.log` | main.py |
| Highlights | `~/.ai-ebook-reader/highlights/<hash>.json` | pdf_highlights_store.py |
| AZW3 Cache | `~/.ai-ebook-reader/cache/azw3/<hash>/` | azw3_reader_backend.py |
| Settings | Windows Registry (QSettings) | app.py |

## Startup Failure Scenarios

| Scenario | Error | Fix |
|----------|-------|-----|
| DB file corrupt | "integrity issues detected" | Delete `library.db`, restart |
| Migration fail | Alembic error in log | Check `migrations/versions/` |
| QML not found | "Failed to load QML" | Check `qml_path` in main.py |
| WebEngine not init | Crash on WebEngineView | Ensure `initialize()` before `QApplication` |
| No display (headless) | "could not connect to display" | Need GUI environment |
