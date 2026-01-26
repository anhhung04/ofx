"""In-memory job registry adapter (default implementation)"""

import logging
from typing import Any

from ofx.runner.registry.base import RegistryAdapter
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MemoryJobRegistry(RegistryAdapter):
    """In-memory implementation of job registry

    This is the default adapter, storing job data in a Python dictionary.
    Data is lost when the process terminates.
    """

    def __init__(self):
        """Initialize the in-memory registry"""
        self._registry: dict[str, dict[str, Any]] = {}
        self._log_debug("Initialized MemoryJobRegistry")

    async def _set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in memory"""
        self._registry[key] = value.copy()
        self._log_debug(f"Set key '{key}' in MemoryJobRegistry")

    async def _get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from memory"""
        return self._registry.get(key)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data"""
        if key in self._registry:
            self._registry[key].update(updates)
        else:
            self._registry[key] = updates.copy()
        self._log_debug(f"Updated key '{key}' in MemoryJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from memory"""
        if key in self._registry:
            del self._registry[key]
            self._log_debug(f"Deleted key '{key}' from MemoryJobRegistry")
            return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in memory"""
        return key in self._registry

    async def _get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from memory"""
        return self._registry.copy()

    async def _clear(self) -> None:
        """Clear all entries from memory"""
        self._registry.clear()
        self._log_debug("Cleared MemoryJobRegistry")

    async def _close(self) -> None:
        """Close the registry (no-op for memory adapter)"""
        self._log_debug("Closed MemoryJobRegistry")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)
