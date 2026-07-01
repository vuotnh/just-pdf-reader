"""Plugin QML controller bridging PluginService to QML views.

Provides a QObject-based controller with signals, slots, and properties
for plugin management including:
- Installed plugins list model with status and metadata
- Enable/disable plugin operations
- Install/uninstall plugin flows
- Hook dispatch triggering from QML

Requirements: 11.1–11.6
"""

from __future__ import annotations

import json
import logging
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    Qt,
    Signal,
    Slot,
)

from src.application.services.plugin_service import PluginService, PluginServiceError
from src.infrastructure.plugins.hook_registry import HookType
from src.infrastructure.plugins.plugin_loader import PluginInfo

logger = logging.getLogger(__name__)


class PluginRoles(IntEnum):
    """Custom roles for PluginListModel data access from QML."""

    PluginIdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    VersionRole = Qt.ItemDataRole.UserRole + 3
    DescriptionRole = Qt.ItemDataRole.UserRole + 4
    EnabledRole = Qt.ItemDataRole.UserRole + 5
    HooksRole = Qt.ItemDataRole.UserRole + 6
    ErrorRole = Qt.ItemDataRole.UserRole + 7
    PermissionsRole = Qt.ItemDataRole.UserRole + 8


class PluginListModel(QAbstractListModel):
    """QAbstractListModel exposing installed plugins to QML.

    Provides role-based data access for the plugin list including
    name, version, description, enabled status, hooks, and errors.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._plugins: list[PluginInfo] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return the number of plugins in the model."""
        if parent.isValid():
            return 0
        return len(self._plugins)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self._plugins):
            return None

        plugin = self._plugins[index.row()]

        if role == PluginRoles.PluginIdRole:
            return plugin.plugin_id
        elif role == PluginRoles.NameRole:
            return plugin.name
        elif role == PluginRoles.VersionRole:
            return plugin.version
        elif role == PluginRoles.DescriptionRole:
            return plugin.description
        elif role == PluginRoles.EnabledRole:
            return plugin.enabled
        elif role == PluginRoles.HooksRole:
            return ", ".join(plugin.hooks)
        elif role == PluginRoles.ErrorRole:
            return plugin.error or ""
        elif role == PluginRoles.PermissionsRole:
            return ", ".join(sorted(plugin.permissions))
        elif role == Qt.ItemDataRole.DisplayRole:
            return plugin.name

        return None

    def roleNames(self) -> dict[int, bytes]:
        """Map role enum values to QML-accessible role name strings."""
        return {
            PluginRoles.PluginIdRole: b"pluginId",
            PluginRoles.NameRole: b"name",
            PluginRoles.VersionRole: b"version",
            PluginRoles.DescriptionRole: b"description",
            PluginRoles.EnabledRole: b"enabled",
            PluginRoles.HooksRole: b"hooks",
            PluginRoles.ErrorRole: b"error",
            PluginRoles.PermissionsRole: b"permissions",
        }

    def set_plugins(self, plugins: list[PluginInfo]) -> None:
        """Replace the entire plugin list and notify views of the change."""
        self.beginResetModel()
        self._plugins = list(plugins)
        self.endResetModel()

    def get_plugins(self) -> list[PluginInfo]:
        """Return the current list of plugins."""
        return list(self._plugins)


class PluginController(QObject):
    """QObject controller bridging PluginService to QML.

    Exposes plugin management operations as slots callable from QML
    and emits signals to notify the UI of state changes. Provides a
    list model for displaying installed plugins with their status.

    The controller supports:
    - Listing all installed plugins with metadata
    - Enabling and disabling plugins
    - Installing plugins from a directory path
    - Uninstalling plugins
    - Dispatching hook events

    Requirements: 11.1–11.6
    """

    # Signals
    pluginsChanged = Signal()
    pluginEnabled = Signal(str)  # plugin_id
    pluginDisabled = Signal(str)  # plugin_id
    pluginInstalled = Signal(str)  # plugin_id
    pluginUninstalled = Signal(str)  # plugin_id
    errorOccurred = Signal(str)  # error message

    def __init__(
        self,
        plugin_service: PluginService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = plugin_service
        self._plugin_model = PluginListModel(self)

        # Load initial plugin list
        self._refresh_plugins()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @Property(QObject, constant=True)
    def pluginModel(self) -> PluginListModel:  # noqa: N802
        """The plugin list model for QML view binding."""
        return self._plugin_model

    @Property(int, notify=pluginsChanged)
    def pluginCount(self) -> int:  # noqa: N802
        """Number of installed plugins."""
        return self._plugin_model.rowCount()

    @Property(int, notify=pluginsChanged)
    def enabledCount(self) -> int:  # noqa: N802
        """Number of currently enabled plugins."""
        return sum(
            1 for p in self._plugin_model.get_plugins() if p.enabled
        )

    # ------------------------------------------------------------------
    # Slots - Plugin Lifecycle
    # ------------------------------------------------------------------

    @Slot(str)
    def installPlugin(self, path: str) -> None:  # noqa: N802
        """Install a plugin from a directory path.

        Copies the plugin source to the plugins directory, validates it,
        and makes it available (disabled by default).

        Args:
            path: Filesystem path to the plugin source directory.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        try:
            from pathlib import Path as PathLib
            info = self._service.install_plugin(PathLib(path))
            self.pluginInstalled.emit(info.plugin_id)
            self._refresh_plugins()
        except PluginServiceError as e:
            self.errorOccurred.emit(str(e))
        except Exception as e:
            logger.exception("Failed to install plugin from: %s", path)
            self.errorOccurred.emit(f"Install failed: {e}")

    @Slot(str)
    def enablePlugin(self, plugin_id: str) -> None:  # noqa: N802
        """Enable a plugin, loading its code and registering hooks.

        Args:
            plugin_id: The identifier of the plugin to enable.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        try:
            self._service.enable_plugin(plugin_id)
            self.pluginEnabled.emit(plugin_id)
            self._refresh_plugins()
        except PluginServiceError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str)
    def disablePlugin(self, plugin_id: str) -> None:  # noqa: N802
        """Disable a plugin without deleting its data.

        Args:
            plugin_id: The identifier of the plugin to disable.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        try:
            self._service.disable_plugin(plugin_id)
            self.pluginDisabled.emit(plugin_id)
            self._refresh_plugins()
        except PluginServiceError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str)
    def uninstallPlugin(self, plugin_id: str) -> None:  # noqa: N802
        """Uninstall a plugin, removing its directory and all hooks.

        Args:
            plugin_id: The identifier of the plugin to uninstall.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        try:
            self._service.uninstall_plugin(plugin_id)
            self.pluginUninstalled.emit(plugin_id)
            self._refresh_plugins()
        except PluginServiceError as e:
            self.errorOccurred.emit(str(e))

    @Slot(str)
    def togglePlugin(self, plugin_id: str) -> None:  # noqa: N802
        """Toggle a plugin's enabled/disabled state.

        Args:
            plugin_id: The identifier of the plugin to toggle.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        plugin = self._service.get_plugin(plugin_id)
        if plugin is None:
            self.errorOccurred.emit(f"Plugin '{plugin_id}' not found")
            return

        if plugin.enabled:
            self.disablePlugin(plugin_id)
        else:
            self.enablePlugin(plugin_id)

    # ------------------------------------------------------------------
    # Slots - Query
    # ------------------------------------------------------------------

    @Slot(str, result=str)
    def getPluginJson(self, plugin_id: str) -> str:  # noqa: N802
        """Get a plugin's full metadata as JSON.

        Args:
            plugin_id: The plugin identifier to retrieve.

        Returns:
            JSON string with plugin data, or empty string if not found.
        """
        if self._service is None:
            return ""

        plugin = self._service.get_plugin(plugin_id)
        if plugin is None:
            return ""

        return json.dumps({
            "pluginId": plugin.plugin_id,
            "name": plugin.name,
            "version": plugin.version,
            "description": plugin.description,
            "enabled": plugin.enabled,
            "hooks": plugin.hooks,
            "permissions": sorted(plugin.permissions),
            "error": plugin.error or "",
        }, ensure_ascii=False)

    @Slot()
    def refresh(self) -> None:
        """Manually refresh the plugin list from the service."""
        self._refresh_plugins()

    @Slot()
    def discoverPlugins(self) -> None:  # noqa: N802
        """Trigger plugin discovery scan.

        Re-scans the plugins directory for new or removed plugins.
        """
        if self._service is None:
            self.errorOccurred.emit("Plugin service not available")
            return

        self._service.discover_plugins()
        self._refresh_plugins()

    # ------------------------------------------------------------------
    # Slots - Hook Dispatch
    # ------------------------------------------------------------------

    @Slot(str, str, result=str)
    def executeHook(self, hook_name: str, context_json: str) -> str:  # noqa: N802
        """Execute a hook and return results as JSON.

        Dispatches the specified hook to all registered plugin handlers
        and returns a JSON array of results.

        Args:
            hook_name: The hook type name (on_word_lookup, on_text_process,
                      on_export, on_import, on_ui_extend).
            context_json: JSON string with the context to pass to handlers.

        Returns:
            JSON array of results from hook handlers.
        """
        if self._service is None:
            return "[]"

        try:
            hook_type = HookType(hook_name)
        except ValueError:
            self.errorOccurred.emit(f"Unknown hook type: {hook_name}")
            return "[]"

        try:
            context: dict[str, Any] = json.loads(context_json) if context_json else {}
        except json.JSONDecodeError:
            self.errorOccurred.emit(f"Invalid context JSON: {context_json}")
            return "[]"

        results = self._service.execute_hook(hook_type, context)

        # Filter None results and serialize
        serializable_results = [r for r in results if r is not None]
        try:
            return json.dumps(serializable_results, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return "[]"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_plugins(self) -> None:
        """Reload plugin list from the service."""
        if self._service is None:
            self._plugin_model.set_plugins([])
            self.pluginsChanged.emit()
            return

        plugins = self._service.get_plugins()
        self._plugin_model.set_plugins(plugins)
        self.pluginsChanged.emit()
