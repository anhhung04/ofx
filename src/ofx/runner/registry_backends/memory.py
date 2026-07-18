"""In-memory job registry adapter (default implementation)"""

import asyncio
from typing import Any

from ofx.runner.registry_adapter import RegistryAdapter

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
        self._log_backend_initialized()

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
            self._registry[key] = self._clone_value(value)
        self._log_backend_key_action("Set", key)

    async def _get(self, key: str) -> Any | None:
        """Retrieve data from memory (returns a deep copy to prevent shared mutation)."""
        async with self._lock:
            value = self._registry.get(key)
            if value is None:
                return None
            return self._clone_value(value)

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data (atomic read-modify-write)."""
        async with self._lock:
            self._registry[key] = self._merged_updated_value(
                self._registry.get(key),
                updates,
            )
        self._log_backend_key_action("Updated", key)

    async def _delete(self, key: str) -> bool:
        """Remove data from memory."""
        async with self._lock:
            if key in self._registry:
                del self._registry[key]
                self._log_backend_key_action("Deleted", key)
                return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in memory."""
        async with self._lock:
            return key in self._registry

    async def _get_all(self) -> dict[str, Any]:
        """Get all entries from memory (deep-copied)."""
        async with self._lock:
            return self._clone_value(self._registry)

    async def _clear(self) -> None:
        """Clear all entries from memory."""
        async with self._lock:
            self._registry.clear()
        self._log_backend_action("Cleared")

    async def _close(self) -> None:
        """Close the registry (no-op for memory adapter)."""
        self._log_backend_action("Closed")
