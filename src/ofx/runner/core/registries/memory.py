"""In-memory job registry adapter (default implementation)"""

import logging
from typing import Any

from ofx.runner.core.registries.base import JobRegistryAdapter
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MemoryJobRegistry(JobRegistryAdapter):
    """In-memory implementation of job registry

    This is the default adapter, storing job data in a Python dictionary.
    Data is lost when the process terminates.
    """

    def __init__(self):
        """Initialize the in-memory registry"""
        self._registry: dict[str, dict[str, Any]] = {}
        logger.debug("Initialized MemoryJobRegistry")

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in memory

        Args:
            key: Unique identifier for the data
            value: Data to store
        """
        self._registry[key] = value.copy()
        logger.debug(f"Set key '{key}' in MemoryJobRegistry")

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from memory

        Args:
            key: Unique identifier for the data

        Returns:
            Data if found, None otherwise
        """
        return self._registry.get(key)

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data

        Args:
            key: Unique identifier for the data
            updates: Fields to update in the data
        """
        if key in self._registry:
            self._registry[key].update(updates)
            logger.debug(f"Updated key '{key}' in MemoryJobRegistry")
        else:
            logger.warning(
                f"Cannot update key '{key}' - not found in MemoryJobRegistry"
            )

    async def delete(self, key: str) -> bool:
        """Remove data from memory

        Args:
            key: Unique identifier for the data

        Returns:
            True if deleted, False if not found
        """
        if key in self._registry:
            del self._registry[key]
            logger.debug(f"Deleted key '{key}' from MemoryJobRegistry")
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check if data exists in memory

        Args:
            key: Unique identifier for the data

        Returns:
            True if data exists, False otherwise
        """
        return key in self._registry

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from memory

        Returns:
            Dictionary mapping keys to their data
        """
        return self._registry.copy()

    async def clear(self) -> None:
        """Clear all entries from memory"""
        self._registry.clear()
        logger.debug("Cleared MemoryJobRegistry")

    async def close(self) -> None:
        """Close the registry (no-op for memory adapter)"""
        logger.debug("Closed MemoryJobRegistry")
