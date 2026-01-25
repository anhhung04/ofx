"""Abstract base class for job registry adapters"""

from abc import ABC, abstractmethod
from typing import Any


class RegistryAdapter(ABC):
    """Abstract base class for job registry implementations using adapter pattern

    This allows different storage backends (memory, Redis, file, etc.) to be used
    interchangeably for job registry operations.
    """

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in the registry

        Args:
            key: Unique identifier for the data (job_id, step_id, workflow_id, etc.)
            value: Data to store (must be JSON-serializable)
        """
        self._validate_key_value(key, value)
        await self._set(key, value)

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from the registry

        Args:
            key: Unique identifier for the data

        Returns:
            Data if found, None otherwise
        """
        self._validate_key(key)
        return await self._get(key)

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data

        Args:
            key: Unique identifier for the data
            updates: Fields to update in the data
        """
        self._validate_key(key)
        self._validate_updates(updates)
        await self._update(key, updates)

    async def delete(self, key: str) -> bool:
        """Remove data from the registry

        Args:
            key: Unique identifier for the data

        Returns:
            True if deleted, False if not found
        """
        self._validate_key(key)
        return await self._delete(key)

    async def exists(self, key: str) -> bool:
        """Check if data exists in the registry

        Args:
            key: Unique identifier for the data

        Returns:
            True if data exists, False otherwise
        """
        self._validate_key(key)
        return await self._exists(key)

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries in the registry

        Returns:
            Dictionary mapping keys to their data
        """
        return await self._get_all()

    async def clear(self) -> None:
        """Clear all entries from the registry"""
        await self._clear()

    async def close(self) -> None:
        """Close any connections or resources used by the adapter"""
        await self._close()

    def _validate_key(self, key: str) -> None:
        """Validate key parameter"""
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Key must be a non-empty string")

    def _validate_key_value(self, key: str, value: Any) -> None:
        """Validate key and value parameters"""
        self._validate_key(key)
        if not isinstance(value, dict):
            raise ValueError("Value must be a dictionary")

    def _validate_updates(self, updates: dict[str, Any]) -> None:
        """Validate updates parameter"""
        if not isinstance(updates, dict):
            raise ValueError("Updates must be a dictionary")

    @abstractmethod
    async def _set(self, key: str, value: dict[str, Any]) -> None:
        """Internal set implementation"""
        pass

    @abstractmethod
    async def _get(self, key: str) -> dict[str, Any] | None:
        """Internal get implementation"""
        pass

    @abstractmethod
    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Internal update implementation"""
        pass

    @abstractmethod
    async def _delete(self, key: str) -> bool:
        """Internal delete implementation"""
        pass

    @abstractmethod
    async def _exists(self, key: str) -> bool:
        """Internal exists implementation"""
        pass

    @abstractmethod
    async def _get_all(self) -> dict[str, dict[str, Any]]:
        """Internal get_all implementation"""
        pass

    @abstractmethod
    async def _clear(self) -> None:
        """Internal clear implementation"""
        pass

    @abstractmethod
    async def _close(self) -> None:
        """Internal close implementation"""
        pass
