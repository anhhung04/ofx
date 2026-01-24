"""Abstract base class for job registry adapters"""

from abc import ABC, abstractmethod
from typing import Any


class RegistryAdapter(ABC):
    """Abstract base class for job registry implementations using adapter pattern

    This allows different storage backends (memory, Redis, file, etc.) to be used
    interchangeably for job registry operations.
    """

    @abstractmethod
    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in the registry

        Args:
            key: Unique identifier for the data (job_id, step_id, workflow_id, etc.)
            value: Data to store (must be JSON-serializable)
        """
        pass

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from the registry

        Args:
            key: Unique identifier for the data

        Returns:
            Data if found, None otherwise
        """
        pass

    @abstractmethod
    async def update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data

        Args:
            key: Unique identifier for the data
            updates: Fields to update in the data
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Remove data from the registry

        Args:
            key: Unique identifier for the data

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if data exists in the registry

        Args:
            key: Unique identifier for the data

        Returns:
            True if data exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries in the registry

        Returns:
            Dictionary mapping keys to their data
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from the registry"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any connections or resources used by the adapter"""
        pass
