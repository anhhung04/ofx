"""In-memory job registry adapter (default implementation)"""

import logging
from typing import Any

from ofx.runner.registry.base import RegistryAdapter
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


_DEFAULT_MAX_SIZE = 100_000


class RegistryOverflowError(RuntimeError):
    """Raised when the in-memory registry exceeds its configured size limit."""


class MemoryJobRegistry(RegistryAdapter):
    """In-memory implementation of job registry

    This is the default adapter, storing job data in a Python dictionary.
    Data is lost when the process terminates.
    """

    def __init__(self, maxsize: int = _DEFAULT_MAX_SIZE):
        """Initialize the in-memory registry

        Args:
            maxsize: Maximum number of keys before RegistryOverflowError is raised.
        """
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self._registry: dict[str, Any] = {}
        self._maxsize = maxsize
        self._log_debug("Initialized MemoryJobRegistry")

    def _check_capacity(self) -> None:
        if len(self._registry) >= self._maxsize:
            raise RegistryOverflowError(
                f"MemoryJobRegistry exceeded maxsize ({self._maxsize}). "
                f"Consider using FileRegistry or RedisJobRegistry for large workloads."
            )

    async def _set(self, key: str, value: Any) -> None:
        """Store data in memory"""
        if key not in self._registry:
            self._check_capacity()
        self._registry[key] = value.copy() if isinstance(value, dict) else value
        self._log_debug(f"Set key '{key}' in MemoryJobRegistry")

    async def _get(self, key: str) -> Any | None:
        """Retrieve data from memory (returns a copy to prevent shared mutation)"""
        value = self._registry.get(key)
        if isinstance(value, dict):
            return value.copy()
        return value

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data"""
        existing = self._registry.get(key)
        if isinstance(existing, dict):
            existing.update(updates)
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

    async def _get_all(self) -> dict[str, Any]:
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
