"""In-memory job registry adapter (default implementation)"""

import asyncio
import copy
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

    All mutating operations are guarded by an :class:`asyncio.Lock` to
    prevent lost-update races when multiple coroutines access the same
    registry concurrently (e.g. parallel job runners writing outputs).
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
        self._lock = asyncio.Lock()
        self._log_debug("Initialized MemoryJobRegistry")

    def _check_capacity(self) -> None:
        if len(self._registry) >= self._maxsize:
            raise RegistryOverflowError(
                f"MemoryJobRegistry exceeded maxsize ({self._maxsize}). "
                f"Consider using FileRegistry or RedisJobRegistry for large workloads."
            )

    async def _set(self, key: str, value: Any) -> None:
        """Store data in memory (deep-copied to isolate mutations)."""
        async with self._lock:
            if key not in self._registry:
                self._check_capacity()
            self._registry[key] = copy.deepcopy(value)
        self._log_debug(f"Set key '{key}' in MemoryJobRegistry")

    async def _get(self, key: str) -> Any | None:
        """Retrieve data from memory (returns a deep copy to prevent shared mutation)."""
        async with self._lock:
            value = self._registry.get(key)
            if value is None:
                return None
            return copy.deepcopy(value)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data (atomic read-modify-write)."""
        async with self._lock:
            existing = self._registry.get(key)
            if isinstance(existing, dict):
                merged = dict(existing)
                merged.update(copy.deepcopy(updates))
                self._registry[key] = merged
            else:
                self._registry[key] = copy.deepcopy(updates)
        self._log_debug(f"Updated key '{key}' in MemoryJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from memory."""
        async with self._lock:
            if key in self._registry:
                del self._registry[key]
                self._log_debug(f"Deleted key '{key}' from MemoryJobRegistry")
                return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in memory."""
        async with self._lock:
            return key in self._registry

    async def _get_all(self) -> dict[str, Any]:
        """Get all entries from memory (deep-copied)."""
        async with self._lock:
            return copy.deepcopy(self._registry)

    async def _clear(self) -> None:
        """Clear all entries from memory."""
        async with self._lock:
            self._registry.clear()
        self._log_debug("Cleared MemoryJobRegistry")

    async def _close(self) -> None:
        """Close the registry (no-op for memory adapter)."""
        self._log_debug("Closed MemoryJobRegistry")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)
