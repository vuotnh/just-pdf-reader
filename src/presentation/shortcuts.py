"""Keyboard shortcut registry for the application.

Provides a central QObject-based registry that maps keyboard sequences
to named actions. QML connects to the triggered signals to execute the
corresponding action handlers.

Standard shortcuts:
- Ctrl+O: Open book
- Ctrl+F: Search
- Ctrl+B: Create bookmark
- Ctrl+L: Toggle left (navigation) panel
- Ctrl+R: Toggle right (side) panel
- Left/Right: Navigate pages
- Ctrl+Plus/Ctrl+Minus: Zoom in/out

Requirements: 14.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShortcutEntry:
    """Definition of a single keyboard shortcut.

    Attributes:
        action: The named action identifier (e.g. "open_book").
        key_sequence: The keyboard sequence string (e.g. "Ctrl+O").
        description: Human-readable description of the action.
    """

    action: str
    key_sequence: str
    description: str


# Default shortcut definitions
DEFAULT_SHORTCUTS: list[ShortcutEntry] = [
    ShortcutEntry("open_book", "Ctrl+O", "Open a book file"),
    ShortcutEntry("search", "Ctrl+F", "Open global search"),
    ShortcutEntry("create_bookmark", "Ctrl+B", "Create bookmark at current position"),
    ShortcutEntry("toggle_left_panel", "Ctrl+L", "Toggle navigation panel"),
    ShortcutEntry("toggle_right_panel", "Ctrl+R", "Toggle side panel"),
    ShortcutEntry("navigate_previous", "Left", "Navigate to previous page"),
    ShortcutEntry("navigate_next", "Right", "Navigate to next page"),
    ShortcutEntry("zoom_in", "Ctrl++", "Zoom in"),
    ShortcutEntry("zoom_out", "Ctrl+-", "Zoom out"),
]


class ShortcutRegistry(QObject):
    """Central keyboard shortcut registry exposed to QML.

    Maps keyboard sequences to named action signals. QML components
    connect to the action signals to handle user input.

    Usage from QML:
        Connections {
            target: shortcutRegistry
            function onOpenBookTriggered() { fileDialog.open() }
            function onSearchTriggered() { searchPanel.activate() }
        }
    """

    # Action signals emitted when shortcuts are activated
    openBookTriggered = Signal()
    searchTriggered = Signal()
    createBookmarkTriggered = Signal()
    toggleLeftPanelTriggered = Signal()
    toggleRightPanelTriggered = Signal()
    navigatePreviousTriggered = Signal()
    navigateNextTriggered = Signal()
    zoomInTriggered = Signal()
    zoomOutTriggered = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._shortcuts: Dict[str, QShortcut] = {}
        self._entries: Dict[str, ShortcutEntry] = {}
        self._signal_map: Dict[str, Signal] = {
            "open_book": self.openBookTriggered,
            "search": self.searchTriggered,
            "create_bookmark": self.createBookmarkTriggered,
            "toggle_left_panel": self.toggleLeftPanelTriggered,
            "toggle_right_panel": self.toggleRightPanelTriggered,
            "navigate_previous": self.navigatePreviousTriggered,
            "navigate_next": self.navigateNextTriggered,
            "zoom_in": self.zoomInTriggered,
            "zoom_out": self.zoomOutTriggered,
        }

    def register_defaults(self, window: QWidget) -> None:
        """Register all default keyboard shortcuts on the given window.

        Creates QShortcut instances attached to the window widget so they
        are active whenever the window has focus.

        Args:
            window: The top-level QWidget (main window) to bind shortcuts to.
        """
        for entry in DEFAULT_SHORTCUTS:
            self.register_shortcut(entry, window)

    def register_shortcut(self, entry: ShortcutEntry, window: QWidget) -> None:
        """Register a single keyboard shortcut.

        Args:
            entry: The shortcut definition to register.
            window: The widget context for the shortcut.
        """
        if entry.action in self._shortcuts:
            # Remove existing shortcut before re-registering
            self._shortcuts[entry.action].deleteLater()

        key_seq = QKeySequence(entry.key_sequence)
        shortcut = QShortcut(key_seq, window)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

        # Connect to the corresponding signal
        signal = self._signal_map.get(entry.action)
        if signal is not None:
            shortcut.activated.connect(signal.emit)
        else:
            logger.warning("No signal mapped for action: %s", entry.action)

        self._shortcuts[entry.action] = shortcut
        self._entries[entry.action] = entry
        logger.debug(
            "Registered shortcut: %s -> %s", entry.key_sequence, entry.action
        )

    def unregister_shortcut(self, action: str) -> None:
        """Remove a registered shortcut by action name.

        Args:
            action: The action identifier to unregister.
        """
        shortcut = self._shortcuts.pop(action, None)
        if shortcut is not None:
            shortcut.deleteLater()
            self._entries.pop(action, None)
            logger.debug("Unregistered shortcut for action: %s", action)

    # ------------------------------------------------------------------
    # QML-accessible slots
    # ------------------------------------------------------------------

    @Slot(str, result=str)
    def getShortcutForAction(self, action: str) -> str:  # noqa: N802
        """Return the key sequence string for a given action.

        Useful for QML to display shortcut hints in tooltips or menus.

        Args:
            action: The action identifier.

        Returns:
            The key sequence string, or empty string if not registered.
        """
        entry = self._entries.get(action)
        return entry.key_sequence if entry else ""

    @Slot(str, result=str)
    def getDescriptionForAction(self, action: str) -> str:  # noqa: N802
        """Return the human-readable description for a given action.

        Args:
            action: The action identifier.

        Returns:
            The description string, or empty string if not registered.
        """
        entry = self._entries.get(action)
        return entry.description if entry else ""

    @Slot(result=list)
    def getAllShortcuts(self) -> list:  # noqa: N802
        """Return all registered shortcuts as a list of dicts.

        Each dict contains: action, keySequence, description.
        Useful for QML settings panels displaying shortcut bindings.

        Returns:
            List of shortcut info dictionaries.
        """
        return [
            {
                "action": entry.action,
                "keySequence": entry.key_sequence,
                "description": entry.description,
            }
            for entry in self._entries.values()
        ]

    @Slot(str)
    def triggerAction(self, action: str) -> None:  # noqa: N802
        """Programmatically trigger an action by name.

        Allows QML toolbar buttons or menu items to invoke the same
        action that keyboard shortcuts trigger.

        Args:
            action: The action identifier to trigger.
        """
        signal = self._signal_map.get(action)
        if signal is not None:
            signal.emit()
        else:
            logger.warning("Cannot trigger unknown action: %s", action)
