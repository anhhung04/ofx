"""Registry adapter abstraction shared by runner registry backends."""

import copy
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class RegistryAdapter(ABC):
    """Abstract base class for job registry implementations using adapter pattern."""

    async def set(self, key: str, value: Any) -> None:
        self._validate_key(key)
        await self._set(key, value)

    async def get(self, key: str) -> Any | None:
        self._validate_key(key)
        return await self._get(key)

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        self._validate_key(key)
        self._validate_updates(updates)
        await self._update(key, updates)

    async def delete(self, key: str) -> bool:
        self._validate_key(key)
        return await self._delete(key)

    async def exists(self, key: str) -> bool:
        self._validate_key(key)
        return await self._exists(key)

    async def get_all(self) -> dict[str, Any]:
        return await self._get_all()

    async def clear(self) -> None:
        await self._clear()

    async def close(self) -> None:
        await self._close()

    def _validate_key(self, key: str) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Key must be a non-empty string")

    def _validate_updates(self, updates: dict[str, Any]) -> None:
        if not isinstance(updates, dict):
            raise ValueError("Updates must be a dictionary")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)

    @staticmethod
    def _clone_value(value: Any) -> Any:
        """Return an isolated copy for local in-process registry backends."""
        return copy.deepcopy(value)

    @staticmethod
    def _serialize_value(key: str, value: Any) -> str | None:
        """Serialize a registry value to JSON, logging failures uniformly."""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to serialize registry value for key '%s': %s", key, exc)
            return None

    @staticmethod
    def _deserialize_value(key: str, value: str | bytes) -> Any | None:
        """Deserialize a registry value from JSON, logging failures uniformly."""
        try:
            if isinstance(value, bytes):
                value = value.decode()
            return json.loads(value)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to decode registry value for key '%s': %s", key, exc)
            return None

    @abstractmethod
    async def _set(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    async def _get(self, key: str) -> Any | None:
        ...

    @abstractmethod
    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def _delete(self, key: str) -> bool:
        ...

    @abstractmethod
    async def _exists(self, key: str) -> bool:
        ...

    @abstractmethod
    async def _get_all(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def _clear(self) -> None:
        ...

    @abstractmethod
    async def _close(self) -> None:
        ...


__all__ = ["RegistryAdapter"]
