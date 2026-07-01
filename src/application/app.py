"""Main application class with startup/shutdown lifecycle management.

Orchestrates application initialization, database setup, service wiring,
crash recovery, data persistence, and graceful shutdown.

Requirements: 12.1, 13.1–13.6
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

from src.infrastructure.database.engine import create_db_engine, get_default_db_path
from src.infrastructure.database.migrations import check_and_run_migrations
from src.infrastructure.database.session import SessionFactory

logger = logging.getLogger(__name__)


class Application(QObject):
    """Main application class managing lifecycle, services, and persistence.

    Handles:
    - Startup: migration check, WAL integrity check, load settings, display main window
    - Shutdown: flush pending changes, save layout state, close database
    - Crash recovery: WAL journal recovery on startup, integrity check
    - Confirmation dialogs for destructive actions
    - Database backup to user-specified location

    The startup sequence is designed to complete within 1 second on SSD.
    """

    # Signals
    startupComplete = Signal()
    shutdownStarted = Signal()
    databaseError = Signal(str)

    def __init__(
        self,
        db_path: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path or get_default_db_path()
        self._engine = None
        self._session_factory: SessionFactory | None = None
        self._settings = QSettings("AIEbookReader", "AI Ebook Reader")
        self._is_running = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def engine(self):
        """The SQLAlchemy database engine."""
        return self._engine

    @property
    def session_factory(self) -> SessionFactory | None:
        """The database session factory."""
        return self._session_factory

    @property
    def settings(self) -> QSettings:
        """Platform-native settings (QSettings)."""
        return self._settings

    @property
    def is_running(self) -> bool:
        """Whether the application startup has completed successfully."""
        return self._is_running

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def startup(self) -> bool:
        """Execute the full startup sequence.

        Sequence:
        1. Create/open database engine with WAL mode
        2. Perform crash recovery (WAL integrity check)
        3. Run pending migrations
        4. Load user settings
        5. Signal startup complete

        Returns:
            True if startup succeeded, False on critical failure.
        """
        start_time = time.perf_counter()
        logger.info("Application startup initiated")

        try:
            # Step 1: Create database engine (WAL mode set via pragmas)
            self._engine = create_db_engine(self._db_path)
            logger.info("Database engine created: %s", self._db_path)

            # Step 2: Crash recovery - WAL integrity check
            self._perform_crash_recovery()

            # Step 3: Run pending migrations
            check_and_run_migrations(self._engine)
            logger.info("Database migrations completed")

            # Step 4: Create session factory
            self._session_factory = SessionFactory(self._engine)

            # Step 5: Load user settings
            self._load_settings()

            self._is_running = True
            elapsed = time.perf_counter() - start_time
            logger.info("Application startup completed in %.3fs", elapsed)
            self.startupComplete.emit()
            return True

        except Exception as e:
            logger.exception("Application startup failed")
            self.databaseError.emit(f"Startup failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Execute the graceful shutdown sequence.

        Sequence:
        1. Signal shutdown started
        2. Flush any pending database changes
        3. Save layout state to QSettings
        4. Close database connections
        """
        if not self._is_running:
            return

        logger.info("Application shutdown initiated")
        self.shutdownStarted.emit()

        try:
            # Step 1: Flush pending changes
            self._flush_pending_changes()

            # Step 2: Save layout state
            self._save_layout_state()

            # Step 3: Close database
            self._close_database()

        except Exception:
            logger.exception("Error during shutdown")
        finally:
            self._is_running = False
            logger.info("Application shutdown completed")

    # ------------------------------------------------------------------
    # Crash Recovery
    # ------------------------------------------------------------------

    def _perform_crash_recovery(self) -> None:
        """Perform crash recovery using SQLite WAL journal.

        SQLite WAL mode provides automatic crash recovery. On startup:
        1. Check if a WAL file exists (indicates potential crash)
        2. Run integrity_check to verify database consistency
        3. Force a WAL checkpoint to consolidate any uncommitted data

        The WAL journal mechanism ensures that the database can recover
        to the last consistent state after an unexpected crash.
        """
        wal_path = Path(str(self._db_path) + "-wal")
        shm_path = Path(str(self._db_path) + "-shm")

        if wal_path.exists():
            logger.info("WAL file detected — performing crash recovery")

        # Run integrity check
        with self._engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA integrity_check")
            rows = result.fetchall()
            if rows and rows[0][0] != "ok":
                integrity_issues = [row[0] for row in rows]
                logger.warning(
                    "Database integrity issues found: %s", integrity_issues
                )
                self.databaseError.emit(
                    f"Database integrity issues detected: {integrity_issues[0]}"
                )
            else:
                logger.info("Database integrity check passed")

            # Force WAL checkpoint to consolidate journal data
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info("WAL checkpoint completed")

    # ------------------------------------------------------------------
    # Settings Management
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        """Load user settings from QSettings (platform-native persistence).

        Settings include panel layout state, reader preferences, and
        application-level configuration.
        """
        logger.info("Loading user settings from QSettings")
        # Settings are loaded on-demand via get_setting/set_setting methods

    def get_setting(self, key: str, default=None):
        """Retrieve a setting value.

        Args:
            key: The setting key (supports hierarchical keys like "layout/navPanelWidth").
            default: Default value if the key is not found.

        Returns:
            The stored setting value, or the default.
        """
        return self._settings.value(key, default)

    def set_setting(self, key: str, value) -> None:
        """Store a setting value.

        Args:
            key: The setting key.
            value: The value to store.
        """
        self._settings.setValue(key, value)

    # ------------------------------------------------------------------
    # Layout State Persistence
    # ------------------------------------------------------------------

    def save_panel_state(
        self,
        nav_panel_visible: bool,
        side_panel_visible: bool,
        nav_panel_width: int,
        side_panel_width: int,
    ) -> None:
        """Save the current panel layout state for session restoration.

        Args:
            nav_panel_visible: Whether the navigation panel is shown.
            side_panel_visible: Whether the side panel is shown.
            nav_panel_width: Current width of the navigation panel.
            side_panel_width: Current width of the side panel.
        """
        self._settings.beginGroup("layout")
        self._settings.setValue("navPanelVisible", nav_panel_visible)
        self._settings.setValue("sidePanelVisible", side_panel_visible)
        self._settings.setValue("navPanelWidth", nav_panel_width)
        self._settings.setValue("sidePanelWidth", side_panel_width)
        self._settings.endGroup()

    def load_panel_state(self) -> dict:
        """Load the saved panel layout state.

        Returns:
            Dictionary with panel state:
            - nav_panel_visible: bool
            - side_panel_visible: bool
            - nav_panel_width: int
            - side_panel_width: int
        """
        self._settings.beginGroup("layout")
        state = {
            "nav_panel_visible": self._settings.value("navPanelVisible", True, type=bool),
            "side_panel_visible": self._settings.value("sidePanelVisible", True, type=bool),
            "nav_panel_width": self._settings.value("navPanelWidth", 250, type=int),
            "side_panel_width": self._settings.value("sidePanelWidth", 300, type=int),
        }
        self._settings.endGroup()
        return state

    def _save_layout_state(self) -> None:
        """Persist current layout state during shutdown.

        Layout state is typically saved incrementally as the user resizes
        panels, but this ensures the final state is captured on exit.
        """
        self._settings.sync()
        logger.info("Layout state saved")

    # ------------------------------------------------------------------
    # Database Operations
    # ------------------------------------------------------------------

    def _flush_pending_changes(self) -> None:
        """Flush any pending database changes before shutdown.

        Forces a WAL checkpoint to ensure all changes are written
        to the main database file.
        """
        if self._engine is None:
            return

        try:
            with self._engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA wal_checkpoint(FULL)")
            logger.info("Pending changes flushed to database")
        except Exception:
            logger.exception("Failed to flush pending changes")

    def _close_database(self) -> None:
        """Close all database connections and dispose of the engine."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connections closed")

    # ------------------------------------------------------------------
    # Database Backup
    # ------------------------------------------------------------------

    @Slot(str, result=bool)
    def backup_database(self, destination: str) -> bool:
        """Create a backup of the database to a user-specified location.

        Performs a safe backup by:
        1. Forcing a WAL checkpoint (consolidate all data)
        2. Copying the main database file to the destination

        Args:
            destination: The file path where the backup should be saved.

        Returns:
            True if backup succeeded, False otherwise.
        """
        dest_path = Path(destination)

        try:
            # Ensure destination directory exists
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Checkpoint WAL to ensure consistency
            if self._engine is not None:
                with self._engine.connect() as conn:
                    conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")

            # Copy the database file
            shutil.copy2(str(self._db_path), str(dest_path))

            logger.info("Database backed up to: %s", dest_path)
            return True

        except Exception as e:
            logger.exception("Database backup failed")
            self.databaseError.emit(f"Backup failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Confirmation Dialogs for Destructive Actions
    # ------------------------------------------------------------------

    @staticmethod
    def confirm_delete_book(book_title: str) -> bool:
        """Show a confirmation dialog before deleting a book.

        Args:
            book_title: The title of the book to delete.

        Returns:
            True if the user confirms deletion, False otherwise.
        """
        reply = QMessageBox.question(
            None,
            "Delete Book",
            f'Are you sure you want to delete "{book_title}"?\n\n'
            "This will also remove all annotations and bookmarks for this book.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    @staticmethod
    def confirm_delete_annotation() -> bool:
        """Show a confirmation dialog before deleting an annotation.

        Returns:
            True if the user confirms deletion, False otherwise.
        """
        reply = QMessageBox.question(
            None,
            "Delete Annotation",
            "Are you sure you want to delete this annotation?\n\n"
            "This will also remove all associated comments.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    @staticmethod
    def confirm_delete_vocabulary(word: str) -> bool:
        """Show a confirmation dialog before deleting a vocabulary entry.

        Args:
            word: The vocabulary word to delete.

        Returns:
            True if the user confirms deletion, False otherwise.
        """
        reply = QMessageBox.question(
            None,
            "Delete Vocabulary Entry",
            f'Are you sure you want to delete "{word}" from your vocabulary?\n\n'
            "This will also remove all associated review cards and history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    @staticmethod
    def confirm_clear_vocabulary() -> bool:
        """Show a confirmation dialog before clearing all vocabulary.

        Returns:
            True if the user confirms clearing, False otherwise.
        """
        reply = QMessageBox.warning(
            None,
            "Clear All Vocabulary",
            "Are you sure you want to delete ALL vocabulary entries?\n\n"
            "This action cannot be undone. All review progress will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes
