"""Plugin service implementing the IPluginService protocol.

Orchestrates plugin lifecycle management including install, enable,
disable, uninstall, and hook execution. Coordinates PluginLoader and
HookRegistry from the infrastructure layer.

Requirements: 11.1–11.6
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from src.infrastructure.plugins.hook_registry import HookRegistry, HookType
from src.infrastructure.plugins.plugin_loader import (
    PluginInfo,
    PluginLoader,
    PluginValidationError,
)

logger = logging.getLogger(__name__)


class PluginServiceError(Exception):
    """Raised when a plugin operation fails."""

    pass


class PluginService:
    """Application-layer service for plugin lifecycle management.

    Implements the IPluginService protocol from the design document,
    coordinating PluginLoader and HookRegistry to handle:
    - Plugin installation from a source path
    - Plugin enable/disable without data deletion
    - Plugin uninstallation (removes plugin directory)
    - Hook execution dispatch to registered plugin handlers
    - Plugin discovery and status querying

    Requirements: 11.1–11.6
    """

    def __init__(
        self,
        plugin_loader: PluginLoader,
        hook_registry: HookRegistry,
    ) -> None:
        """Initialize the plugin service.

        Args:
            plugin_loader: Infrastructure layer plugin loader for discovery/loading.
            hook_registry: Infrastructure layer hook registry for event dispatch.
        """
        self._loader = plugin_loader
        self._registry = hook_registry

    # ------------------------------------------------------------------
    # Plugin Discovery (Requirement 11.6)
    # ------------------------------------------------------------------

    def discover_plugins(self) -> list[PluginInfo]:
        """Discover all plugins in the plugins directory.

        Scans the plugins directory for valid plugin structures and
        returns metadata for all discovered plugins.

        Returns:
            List of PluginInfo for all discovered plugins.
        """
        return self._loader.discover_plugins()

    # ------------------------------------------------------------------
    # Plugin Install (Requirement 11.2)
    # ------------------------------------------------------------------

    def install_plugin(self, path: Path) -> PluginInfo:
        """Install a plugin from a source directory path.

        Copies the plugin directory to the plugins directory, validates
        the plugin structure, and registers it as available (disabled).

        Args:
            path: Path to the plugin source directory containing plugin.json
                  and main.py.

        Returns:
            PluginInfo for the newly installed plugin.

        Raises:
            PluginServiceError: If the path is invalid or installation fails.
        """
        if not path.exists():
            raise PluginServiceError(f"Plugin path does not exist: {path}")

        if not path.is_dir():
            raise PluginServiceError(
                f"Plugin path must be a directory: {path}"
            )

        # Validate source has required files before copying
        if not (path / "plugin.json").exists():
            raise PluginServiceError(
                f"Plugin directory missing plugin.json: {path}"
            )
        if not (path / "main.py").exists():
            raise PluginServiceError(
                f"Plugin directory missing main.py: {path}"
            )

        # Determine plugin ID from directory name
        plugin_id = path.name
        target_dir = self._loader.plugins_dir / plugin_id

        # Check if already installed
        if target_dir.exists():
            raise PluginServiceError(
                f"Plugin '{plugin_id}' is already installed"
            )

        # Copy plugin directory to the plugins directory
        try:
            self._loader.plugins_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(path, target_dir)
        except OSError as e:
            raise PluginServiceError(
                f"Failed to install plugin '{plugin_id}': {e}"
            )

        # Re-discover to pick up the new plugin
        self._loader.discover_plugins()

        info = self._loader.get_plugin_info(plugin_id)
        if info is None:
            raise PluginServiceError(
                f"Plugin '{plugin_id}' was copied but failed discovery"
            )

        if info.error:
            raise PluginServiceError(
                f"Plugin '{plugin_id}' has validation errors: {info.error}"
            )

        logger.info("Plugin '%s' installed successfully", plugin_id)
        return info

    # ------------------------------------------------------------------
    # Plugin Enable/Disable (Requirement 11.3)
    # ------------------------------------------------------------------

    def enable_plugin(self, plugin_id: str) -> None:
        """Enable a plugin, loading its code and registering hooks.

        Args:
            plugin_id: Unique identifier of the plugin to enable.

        Raises:
            PluginServiceError: If the plugin is not found or fails to load.
        """
        info = self._loader.get_plugin_info(plugin_id)
        if info is None:
            raise PluginServiceError(f"Plugin '{plugin_id}' not found")

        success = self._loader.enable_plugin(plugin_id)
        if not success:
            # Retrieve updated info for error details
            updated_info = self._loader.get_plugin_info(plugin_id)
            error_msg = updated_info.error if updated_info else "Unknown error"
            raise PluginServiceError(
                f"Failed to enable plugin '{plugin_id}': {error_msg}"
            )

        logger.info("Plugin '%s' enabled", plugin_id)

    def disable_plugin(self, plugin_id: str) -> None:
        """Disable a plugin, unregistering hooks without deleting data.

        Args:
            plugin_id: Unique identifier of the plugin to disable.

        Raises:
            PluginServiceError: If the plugin is not found.
        """
        info = self._loader.get_plugin_info(plugin_id)
        if info is None:
            raise PluginServiceError(f"Plugin '{plugin_id}' not found")

        success = self._loader.disable_plugin(plugin_id)
        if not success:
            raise PluginServiceError(
                f"Failed to disable plugin '{plugin_id}'"
            )

        logger.info("Plugin '%s' disabled (data preserved)", plugin_id)

    # ------------------------------------------------------------------
    # Plugin Uninstall
    # ------------------------------------------------------------------

    def uninstall_plugin(self, plugin_id: str) -> None:
        """Uninstall a plugin by disabling it and removing its directory.

        Args:
            plugin_id: Unique identifier of the plugin to uninstall.

        Raises:
            PluginServiceError: If the plugin is not found or removal fails.
        """
        info = self._loader.get_plugin_info(plugin_id)
        if info is None:
            raise PluginServiceError(f"Plugin '{plugin_id}' not found")

        # Disable first if currently enabled
        if info.enabled:
            self._loader.disable_plugin(plugin_id)

        # Remove plugin directory
        plugin_dir = info.path
        try:
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
        except OSError as e:
            raise PluginServiceError(
                f"Failed to remove plugin directory '{plugin_id}': {e}"
            )

        # Re-discover to update internal state
        self._loader.discover_plugins()

        logger.info("Plugin '%s' uninstalled and removed", plugin_id)

    # ------------------------------------------------------------------
    # Plugin Query (Requirement 11.6)
    # ------------------------------------------------------------------

    def get_plugins(self) -> list[PluginInfo]:
        """Get a list of all installed plugins with their status.

        Returns:
            List of PluginInfo objects with current enabled/disabled status.
        """
        return list(self._loader.plugins.values())

    def get_plugin(self, plugin_id: str) -> PluginInfo | None:
        """Get info for a specific plugin.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            PluginInfo if found, None otherwise.
        """
        return self._loader.get_plugin_info(plugin_id)

    # ------------------------------------------------------------------
    # Hook Execution (Requirement 11.1, 11.4, 11.5)
    # ------------------------------------------------------------------

    def execute_hook(self, hook: HookType, context: dict[str, Any]) -> list[Any]:
        """Execute a hook, dispatching to all registered plugin handlers.

        Handlers are called in registration order. Errors in individual
        plugins are caught and logged without affecting other handlers
        or the main application (Requirements 11.4, 11.5).

        Args:
            hook: The hook type to dispatch (on_word_lookup, on_text_process,
                  on_export, on_import, on_ui_extend).
            context: Context dictionary passed to each handler.

        Returns:
            List of results from handlers that completed successfully.
        """
        return self._registry.dispatch(hook, context)

    def execute_on_word_lookup(self, word: str, **kwargs: Any) -> list[Any]:
        """Execute the on_word_lookup hook for additional definitions.

        Args:
            word: The word being looked up.
            **kwargs: Additional context (e.g., language, book_id).

        Returns:
            List of additional definition results from plugins.
        """
        context = {"word": word, **kwargs}
        return self.execute_hook(HookType.ON_WORD_LOOKUP, context)

    def execute_on_text_process(self, text: str, **kwargs: Any) -> list[Any]:
        """Execute the on_text_process hook for text transformation.

        Args:
            text: The text to process (TTS, translation, etc.).
            **kwargs: Additional context.

        Returns:
            List of processed text results from plugins.
        """
        context = {"text": text, **kwargs}
        return self.execute_hook(HookType.ON_TEXT_PROCESS, context)

    def execute_on_export(
        self, annotations: list[dict[str, Any]], format: str, **kwargs: Any
    ) -> list[Any]:
        """Execute the on_export hook for custom export formats.

        Args:
            annotations: The annotations to export.
            format: The export format identifier.
            **kwargs: Additional context.

        Returns:
            List of export results from plugins.
        """
        context = {"annotations": annotations, "format": format, **kwargs}
        return self.execute_hook(HookType.ON_EXPORT, context)

    def execute_on_import(self, file_path: str, **kwargs: Any) -> list[Any]:
        """Execute the on_import hook for custom file format support.

        Args:
            file_path: Path to the file to import.
            **kwargs: Additional context.

        Returns:
            List of import results from plugins.
        """
        context = {"file_path": file_path, **kwargs}
        return self.execute_hook(HookType.ON_IMPORT, context)

    def execute_on_ui_extend(self, panel: str, **kwargs: Any) -> list[Any]:
        """Execute the on_ui_extend hook for custom UI panel registration.

        Args:
            panel: The panel identifier being extended.
            **kwargs: Additional context.

        Returns:
            List of UI extension results from plugins.
        """
        context = {"panel": panel, **kwargs}
        return self.execute_hook(HookType.ON_UI_EXTEND, context)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def has_hook_handlers(self, hook: HookType) -> bool:
        """Check whether any plugins are registered for a hook type.

        Args:
            hook: The hook type to check.

        Returns:
            True if at least one handler is registered.
        """
        return self._registry.has_handlers(hook)
