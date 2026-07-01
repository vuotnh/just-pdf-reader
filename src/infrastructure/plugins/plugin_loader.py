"""Plugin loader with discovery, validation, sandboxed loading, and lifecycle.

Handles plugin discovery from the plugins directory, validates plugin.json
metadata, loads plugin code in a restricted sandbox, and manages
enable/disable lifecycle without data deletion.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.infrastructure.plugins.hook_registry import HookRegistry, HookType

logger = logging.getLogger(__name__)

# Maximum execution time for plugin hook calls (seconds)
PLUGIN_TIMEOUT_SECONDS = 5

# Required fields in plugin.json
REQUIRED_METADATA_FIELDS = {"name", "version", "hooks"}

# Valid hook names that plugins can register
VALID_HOOK_NAMES = {hook.value for hook in HookType}

# Valid permission declarations
VALID_PERMISSIONS = {"network", "file_read", "file_write"}


class PluginValidationError(Exception):
    """Raised when a plugin fails structure or metadata validation."""

    pass


@dataclass
class PluginInfo:
    """Metadata and state for a loaded plugin.

    Attributes:
        plugin_id: Unique identifier derived from plugin directory name.
        name: Human-readable plugin name from plugin.json.
        version: Plugin version string.
        description: Optional plugin description.
        hooks: List of hook names this plugin registers.
        permissions: Set of permissions the plugin declares.
        path: Path to the plugin directory.
        enabled: Whether the plugin is currently active.
        error: Last error message if the plugin failed to load/execute.
    """

    plugin_id: str
    name: str
    version: str
    description: str = ""
    hooks: list[str] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    path: Path = field(default_factory=lambda: Path("."))
    enabled: bool = False
    error: str | None = None


class PluginLoader:
    """Discovers, validates, loads, and manages plugins.

    Plugins are loaded from a plugins directory, each in their own subdirectory
    containing:
      - plugin.json (metadata: name, version, description, hooks, permissions)
      - main.py (entry point with hook implementations)

    Plugin code is executed in a restricted sandbox with:
      - No access to dangerous builtins (__import__, eval, exec, compile)
      - File I/O restricted to the plugin's own directory
      - Network access only if declared in permissions
      - Execution timeout of 5 seconds per hook invocation
    """

    def __init__(
        self,
        plugins_dir: Path,
        hook_registry: HookRegistry,
    ) -> None:
        """Initialize the plugin loader.

        Args:
            plugins_dir: Directory containing plugin subdirectories.
            hook_registry: The hook registry to register plugin handlers with.
        """
        self._plugins_dir = plugins_dir
        self._hook_registry = hook_registry
        self._plugins: dict[str, PluginInfo] = {}
        self._plugin_modules: dict[str, dict[str, Any]] = {}

    @property
    def plugins_dir(self) -> Path:
        """Return the plugins directory path."""
        return self._plugins_dir

    @property
    def plugins(self) -> dict[str, PluginInfo]:
        """Return a copy of all discovered plugins."""
        return dict(self._plugins)

    def discover_plugins(self) -> list[PluginInfo]:
        """Discover all plugins in the plugins directory.

        Scans subdirectories of the plugins directory for valid plugin
        structures (containing plugin.json). Validates each plugin's metadata.

        Returns:
            List of PluginInfo for all discovered (valid or invalid) plugins.
        """
        discovered: list[PluginInfo] = []

        if not self._plugins_dir.exists():
            logger.info("Plugins directory does not exist: %s", self._plugins_dir)
            return discovered

        for entry in sorted(self._plugins_dir.iterdir()):
            if not entry.is_dir():
                continue
            plugin_id = entry.name
            try:
                info = self._validate_plugin(plugin_id, entry)
                self._plugins[plugin_id] = info
                discovered.append(info)
            except PluginValidationError as e:
                error_info = PluginInfo(
                    plugin_id=plugin_id,
                    name=plugin_id,
                    version="unknown",
                    path=entry,
                    error=str(e),
                )
                self._plugins[plugin_id] = error_info
                discovered.append(error_info)
                logger.warning("Plugin '%s' validation failed: %s", plugin_id, e)

        return discovered

    def _validate_plugin(self, plugin_id: str, plugin_dir: Path) -> PluginInfo:
        """Validate plugin structure and metadata.

        Checks:
          - plugin.json exists and is valid JSON
          - Required fields are present (name, version, hooks)
          - Hook names are valid
          - main.py exists as the entry point

        Args:
            plugin_id: The directory name used as the plugin identifier.
            plugin_dir: Path to the plugin directory.

        Returns:
            PluginInfo with validated metadata.

        Raises:
            PluginValidationError: If validation fails.
        """
        # Check plugin.json exists
        metadata_path = plugin_dir / "plugin.json"
        if not metadata_path.exists():
            raise PluginValidationError(
                f"Missing plugin.json in '{plugin_dir}'"
            )

        # Parse plugin.json
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise PluginValidationError(
                f"Invalid plugin.json in '{plugin_id}': {e}"
            )

        # Validate required fields
        missing = REQUIRED_METADATA_FIELDS - set(metadata.keys())
        if missing:
            raise PluginValidationError(
                f"Plugin '{plugin_id}' missing required fields: {missing}"
            )

        # Validate hooks
        hooks = metadata.get("hooks", [])
        if not isinstance(hooks, list):
            raise PluginValidationError(
                f"Plugin '{plugin_id}' 'hooks' must be a list"
            )
        invalid_hooks = set(hooks) - VALID_HOOK_NAMES
        if invalid_hooks:
            raise PluginValidationError(
                f"Plugin '{plugin_id}' has invalid hooks: {invalid_hooks}"
            )

        # Validate permissions (optional)
        permissions = set(metadata.get("permissions", []))
        invalid_perms = permissions - VALID_PERMISSIONS
        if invalid_perms:
            raise PluginValidationError(
                f"Plugin '{plugin_id}' has invalid permissions: {invalid_perms}"
            )

        # Check main.py exists
        main_path = plugin_dir / "main.py"
        if not main_path.exists():
            raise PluginValidationError(
                f"Missing main.py in plugin '{plugin_id}'"
            )

        return PluginInfo(
            plugin_id=plugin_id,
            name=metadata.get("name", plugin_id),
            version=metadata.get("version", "0.0.0"),
            description=metadata.get("description", ""),
            hooks=hooks,
            permissions=permissions,
            path=plugin_dir,
            enabled=False,
        )

    def load_plugin(self, plugin_id: str) -> bool:
        """Load and enable a plugin by executing its main.py in a sandbox.

        The plugin code runs in a restricted namespace. Hook functions defined
        in main.py are registered with the hook registry.

        Args:
            plugin_id: Identifier of the plugin to load.

        Returns:
            True if the plugin was loaded successfully, False otherwise.
        """
        info = self._plugins.get(plugin_id)
        if info is None:
            logger.error("Plugin '%s' not found", plugin_id)
            return False

        if info.error:
            logger.error(
                "Cannot load plugin '%s' with validation error: %s",
                plugin_id,
                info.error,
            )
            return False

        if info.enabled:
            logger.debug("Plugin '%s' is already loaded", plugin_id)
            return True

        main_path = info.path / "main.py"
        try:
            with open(main_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except OSError as e:
            info.error = f"Failed to read main.py: {e}"
            logger.error("Plugin '%s': %s", plugin_id, info.error)
            return False

        # Build sandbox globals
        sandbox_globals = self._build_sandbox_globals(info)

        # Execute plugin code in sandbox with timeout
        try:
            success = self._execute_with_timeout(
                source_code, sandbox_globals, plugin_id
            )
        except Exception as e:
            info.error = f"Plugin execution failed: {e}"
            logger.exception("Plugin '%s' failed to load", plugin_id)
            return False

        if not success:
            info.error = "Plugin execution timed out"
            logger.error("Plugin '%s' timed out during loading", plugin_id)
            return False

        # Store the module namespace and register hooks
        self._plugin_modules[plugin_id] = sandbox_globals
        self._register_hooks(info, sandbox_globals)

        info.enabled = True
        info.error = None
        logger.info("Plugin '%s' loaded and enabled", plugin_id)
        return True

    def unload_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin without deleting its data.

        Unregisters all hooks and removes the module namespace, but preserves
        the plugin directory and metadata.

        Args:
            plugin_id: Identifier of the plugin to disable.

        Returns:
            True if the plugin was disabled successfully, False otherwise.
        """
        info = self._plugins.get(plugin_id)
        if info is None:
            logger.error("Plugin '%s' not found", plugin_id)
            return False

        if not info.enabled:
            logger.debug("Plugin '%s' is already disabled", plugin_id)
            return True

        # Unregister all hooks
        self._hook_registry.unregister(plugin_id)

        # Remove module namespace
        self._plugin_modules.pop(plugin_id, None)

        info.enabled = False
        logger.info("Plugin '%s' disabled (data preserved)", plugin_id)
        return True

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a previously disabled plugin.

        Reloads the plugin code and re-registers hooks.

        Args:
            plugin_id: Identifier of the plugin to enable.

        Returns:
            True if the plugin was enabled successfully.
        """
        return self.load_plugin(plugin_id)

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin without data deletion.

        Args:
            plugin_id: Identifier of the plugin to disable.

        Returns:
            True if the plugin was disabled successfully.
        """
        return self.unload_plugin(plugin_id)

    def get_plugin_info(self, plugin_id: str) -> PluginInfo | None:
        """Get info for a specific plugin.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            PluginInfo if found, None otherwise.
        """
        return self._plugins.get(plugin_id)

    # Standard library modules that plugins are allowed to import
    ALLOWED_MODULES = frozenset({
        "json",
        "re",
        "math",
        "datetime",
        "collections",
        "itertools",
        "functools",
        "string",
        "time",
        "hashlib",
        "base64",
        "pathlib",
        "dataclasses",
        "typing",
        "enum",
        "copy",
        "textwrap",
    })

    # Modules that require 'network' permission
    NETWORK_MODULES = frozenset({
        "urllib",
        "urllib.request",
        "urllib.parse",
        "http",
        "http.client",
    })

    def _build_sandbox_globals(self, info: PluginInfo) -> dict[str, Any]:
        """Build restricted globals for plugin sandbox execution.

        Provides:
          - Safe builtins (no eval, exec, compile, breakpoint)
          - A restricted __import__ allowing only safe standard library modules
          - A restricted open() that limits file I/O to the plugin's own directory
          - Network module access only if declared in permissions

        Args:
            info: Plugin metadata including path and permissions.

        Returns:
            Dictionary of globals for exec().
        """
        # Safe subset of builtins
        safe_builtins = {
            k: v
            for k, v in __builtins__.items()  # type: ignore[union-attr]
            if k not in ("eval", "exec", "compile", "open", "breakpoint")
        } if isinstance(__builtins__, dict) else {
            k: getattr(__builtins__, k)
            for k in dir(__builtins__)
            if k not in ("eval", "exec", "compile", "open", "breakpoint")
            and not k.startswith("_")
        }

        # Build restricted __import__ allowing only safe modules
        has_network = "network" in info.permissions
        allowed = self.ALLOWED_MODULES | (self.NETWORK_MODULES if has_network else frozenset())

        def restricted_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            """Import only from the allowed module whitelist."""
            # Check the top-level module name
            top_level = name.split(".")[0]
            if top_level not in allowed and name not in allowed:
                raise ImportError(
                    f"Plugin '{info.plugin_id}' is not allowed to import '{name}'. "
                    f"Allowed modules: {sorted(allowed)}"
                )
            import importlib
            return importlib.import_module(name)

        safe_builtins["__import__"] = restricted_import

        # Add restricted open for file I/O within plugin directory only
        plugin_dir = info.path.resolve()

        def restricted_open(
            filepath: str, mode: str = "r", *args: Any, **kwargs: Any
        ) -> Any:
            """Open files only within the plugin's own directory."""
            resolved = Path(filepath).resolve()
            # Ensure the path is within the plugin directory
            try:
                resolved.relative_to(plugin_dir)
            except ValueError:
                raise PermissionError(
                    f"Plugin '{info.plugin_id}' cannot access files outside "
                    f"its directory: {filepath}"
                )
            return open(resolved, mode, *args, **kwargs)

        safe_builtins["open"] = restricted_open

        sandbox = {
            "__builtins__": safe_builtins,
            "__name__": f"plugin_{info.plugin_id}",
            "__file__": str(info.path / "main.py"),
            "PLUGIN_DIR": str(plugin_dir),
            "PLUGIN_ID": info.plugin_id,
            "PLUGIN_PERMISSIONS": info.permissions,
        }

        return sandbox

    def _execute_with_timeout(
        self, source_code: str, sandbox_globals: dict[str, Any], plugin_id: str
    ) -> bool:
        """Execute plugin source code with a timeout.

        Uses a thread with a deadline. If the plugin code does not complete
        within PLUGIN_TIMEOUT_SECONDS, execution is considered failed.

        Args:
            source_code: The Python source code to execute.
            sandbox_globals: The restricted globals namespace.
            plugin_id: Plugin identifier for logging.

        Returns:
            True if execution completed within the timeout, False otherwise.
        """
        error_holder: list[Exception] = []
        completed = threading.Event()

        def _run() -> None:
            try:
                compiled = compile(
                    source_code, f"<plugin:{plugin_id}>", "exec"
                )
                exec(compiled, sandbox_globals)  # noqa: S102
            except Exception as e:
                error_holder.append(e)
            finally:
                completed.set()

        thread = threading.Thread(
            target=_run, name=f"plugin-load-{plugin_id}", daemon=True
        )
        thread.start()
        thread.join(timeout=PLUGIN_TIMEOUT_SECONDS)

        if not completed.is_set():
            logger.error(
                "Plugin '%s' timed out after %d seconds during load",
                plugin_id,
                PLUGIN_TIMEOUT_SECONDS,
            )
            return False

        if error_holder:
            raise error_holder[0]

        return True

    def _register_hooks(
        self, info: PluginInfo, namespace: dict[str, Any]
    ) -> None:
        """Register plugin hook functions with the hook registry.

        Looks for functions in the plugin namespace matching declared hook names
        and wraps them with timeout protection before registering.

        Args:
            info: Plugin metadata with declared hooks.
            namespace: The plugin's executed namespace containing hook functions.
        """
        for hook_name in info.hooks:
            handler = namespace.get(hook_name)
            if handler is None:
                logger.warning(
                    "Plugin '%s' declares hook '%s' but does not define it",
                    info.plugin_id,
                    hook_name,
                )
                continue

            if not callable(handler):
                logger.warning(
                    "Plugin '%s' hook '%s' is not callable",
                    info.plugin_id,
                    hook_name,
                )
                continue

            # Wrap handler with timeout and error protection
            wrapped = self._wrap_handler(info.plugin_id, hook_name, handler)

            hook_type = HookType(hook_name)
            self._hook_registry.register(hook_type, info.plugin_id, wrapped)

    def _wrap_handler(
        self, plugin_id: str, hook_name: str, handler: Callable[..., Any]
    ) -> Callable[..., Any]:
        """Wrap a plugin handler with timeout and error catching.

        The wrapped handler:
          - Executes the original handler in a thread with a timeout
          - Catches any exceptions and logs them
          - Returns None on timeout or error

        Args:
            plugin_id: Plugin identifier for logging.
            hook_name: Name of the hook for logging.
            handler: The original handler callable.

        Returns:
            Wrapped handler function.
        """

        def _wrapped_handler(context: dict[str, Any]) -> Any:
            result_holder: list[Any] = []
            error_holder: list[Exception] = []
            completed = threading.Event()

            def _run() -> None:
                try:
                    result = handler(context)
                    result_holder.append(result)
                except Exception as e:
                    error_holder.append(e)
                finally:
                    completed.set()

            thread = threading.Thread(
                target=_run,
                name=f"plugin-hook-{plugin_id}-{hook_name}",
                daemon=True,
            )
            thread.start()
            thread.join(timeout=PLUGIN_TIMEOUT_SECONDS)

            if not completed.is_set():
                logger.error(
                    "Plugin '%s' hook '%s' timed out after %d seconds",
                    plugin_id,
                    hook_name,
                    PLUGIN_TIMEOUT_SECONDS,
                )
                return None

            if error_holder:
                logger.exception(
                    "Plugin '%s' hook '%s' raised an error: %s",
                    plugin_id,
                    hook_name,
                    error_holder[0],
                )
                return None

            return result_holder[0] if result_holder else None

        return _wrapped_handler
