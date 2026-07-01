"""Hook registry for plugin event dispatch.

The HookRegistry is the central dispatcher that routes events to registered
plugin hooks. Each hook type represents an extension point in the application.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookType(Enum):
    """Available plugin hook extension points."""

    ON_WORD_LOOKUP = "on_word_lookup"
    ON_TEXT_PROCESS = "on_text_process"
    ON_EXPORT = "on_export"
    ON_IMPORT = "on_import"
    ON_UI_EXTEND = "on_ui_extend"


class HookRegistry:
    """Central dispatcher that routes events to registered plugin hooks.

    Plugins register callable handlers for specific hook types. When a hook
    is dispatched, all registered handlers for that hook type are called in
    registration order.

    Attributes:
        _hooks: Mapping from HookType to list of (plugin_id, handler) tuples.
    """

    def __init__(self) -> None:
        """Initialize an empty hook registry."""
        self._hooks: dict[HookType, list[tuple[str, Callable[..., Any]]]] = {
            hook_type: [] for hook_type in HookType
        }

    def register(
        self, hook_type: HookType, plugin_id: str, handler: Callable[..., Any]
    ) -> None:
        """Register a handler for a specific hook type.

        Args:
            hook_type: The hook extension point to register for.
            plugin_id: Unique identifier of the plugin registering the hook.
            handler: Callable to invoke when the hook is dispatched.

        Raises:
            ValueError: If hook_type is not a valid HookType.
        """
        if hook_type not in self._hooks:
            raise ValueError(f"Unknown hook type: {hook_type}")
        self._hooks[hook_type].append((plugin_id, handler))
        logger.debug(
            "Plugin '%s' registered handler for hook '%s'",
            plugin_id,
            hook_type.value,
        )

    def unregister(self, plugin_id: str) -> None:
        """Unregister all hooks for a specific plugin.

        Args:
            plugin_id: The plugin whose hooks should be removed.
        """
        for hook_type in self._hooks:
            self._hooks[hook_type] = [
                (pid, handler)
                for pid, handler in self._hooks[hook_type]
                if pid != plugin_id
            ]
        logger.debug("Unregistered all hooks for plugin '%s'", plugin_id)

    def dispatch(
        self, hook_type: HookType, context: dict[str, Any] | None = None
    ) -> list[Any]:
        """Dispatch a hook event to all registered handlers.

        Calls each registered handler in registration order. If a handler
        raises an exception, it is caught and logged, and the remaining
        handlers continue execution.

        Args:
            hook_type: The hook event to dispatch.
            context: Context dictionary passed to each handler.

        Returns:
            List of results from each handler that completed successfully.
        """
        if context is None:
            context = {}

        results: list[Any] = []
        handlers = self._hooks.get(hook_type, [])

        for plugin_id, handler in handlers:
            try:
                result = handler(context)
                results.append(result)
            except Exception:
                logger.exception(
                    "Plugin '%s' raised an error in hook '%s'",
                    plugin_id,
                    hook_type.value,
                )
                # Continue executing other handlers — error isolation

        return results

    def get_handlers(self, hook_type: HookType) -> list[tuple[str, Callable[..., Any]]]:
        """Get all registered handlers for a hook type.

        Args:
            hook_type: The hook type to query.

        Returns:
            List of (plugin_id, handler) tuples in registration order.
        """
        return list(self._hooks.get(hook_type, []))

    def has_handlers(self, hook_type: HookType) -> bool:
        """Check whether any handlers are registered for a hook type.

        Args:
            hook_type: The hook type to check.

        Returns:
            True if at least one handler is registered.
        """
        return len(self._hooks.get(hook_type, [])) > 0

    def clear(self) -> None:
        """Remove all registered hooks from the registry."""
        for hook_type in self._hooks:
            self._hooks[hook_type] = []
        logger.debug("Hook registry cleared")
