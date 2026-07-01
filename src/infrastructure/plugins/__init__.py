"""Plugin infrastructure: discovery, loading, isolation, and hook dispatch.

Implements the plugin system with:
  - Plugin discovery and validation (plugin.json schema check)
  - Sandboxed execution with restricted globals
  - Hook registry for routing events to registered plugin hooks
  - Plugin enable/disable without data deletion
"""

from src.infrastructure.plugins.hook_registry import HookRegistry, HookType
from src.infrastructure.plugins.plugin_loader import (
    PluginInfo,
    PluginLoader,
    PluginValidationError,
)

__all__ = [
    "HookRegistry",
    "HookType",
    "PluginInfo",
    "PluginLoader",
    "PluginValidationError",
]
