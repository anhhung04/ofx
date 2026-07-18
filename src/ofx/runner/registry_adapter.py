"""Registry adapter abstraction shared by runner registry backends."""

import copy
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

class RegistryAdapter(ABC):
    """Abstract base class for job registry implementations using adapter pattern."""

    _backend_display_name: str | None = None

    async def set(self, key: str, value: Any) -> None:
        await self._validated_key_call(self._set, key, value)

    async def get(self, key: str) -> Any | None:
        return await self._validated_key_call(self._get, key)

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        await self._validated_update_call(key, updates)

    async def delete(self, key: str) -> bool:
        return await self._validated_key_call(self._delete, key)

    async def exists(self, key: str) -> bool:
        return await self._validated_key_call(self._exists, key)

    async def get_all(self) -> dict[str, Any]:
        return await self._get_all()

    async def clear(self) -> None:
        await self._clear()

    async def close(self) -> None:
        await self._close()

    async def _validated_key_call(self, method, key: str, *args):
        self._validate_key(key)
        return await method(key, *args)

    async def _validated_update_call(self, key: str, updates: dict[str, Any]) -> None:
        self._validate_key(key)
        self._validate_updates(updates)
        await self._update(key, updates)

    def _validate_key(self, key: str) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Key must be a non-empty string")

    def _validate_updates(self, updates: dict[str, Any]) -> None:
        if not isinstance(updates, dict):
            raise ValueError("Updates must be a dictionary")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)

    def _backend_name(self) -> str:
        return self._backend_display_name or type(self).__name__

    def _log_backend_initialized(self, details: str = "") -> None:
        suffix = f" {details}" if details else ""
        self._log_debug(f"Initialized {self._backend_name()}{suffix}")

    def _log_backend_key_action(self, action: str, key: str) -> None:
        self._log_debug(f"{action} key '{key}' in {self._backend_name()}")

    def _log_backend_action(self, action: str) -> None:
        self._log_debug(f"{action} {self._backend_name()}")

    @staticmethod
    def _clone_value(value: Any) -> Any:
        """Return an isolated copy for local in-process registry backends."""
        return copy.deepcopy(value)

    @classmethod
    def _merged_updated_value(cls, existing: Any, updates: dict[str, Any]) -> Any:
        """Return the backend-safe merged value for an update operation."""
        if isinstance(existing, dict):
            merged = cls._clone_value(existing)
            merged.update(cls._clone_value(updates))
            return merged
        return cls._clone_value(updates)

    @staticmethod
    def _normalized_prefix(prefix: str, separator: str = "") -> str:
        """Normalize a backend key prefix with an optional trailing separator."""
        if not separator:
            return prefix
        return prefix if prefix.endswith(separator) else f"{prefix}{separator}"

    @classmethod
    def _prefixed_key(cls, prefix: str, key: str, separator: str = "") -> str:
        """Build a backend storage key from a logical key and prefix."""
        return f"{cls._normalized_prefix(prefix, separator)}{key}"

    @classmethod
    def _unprefixed_key(cls, prefixed_key: str, prefix: str, separator: str = "") -> str:
        """Strip a normalized prefix from a backend storage key."""
        return prefixed_key[len(cls._normalized_prefix(prefix, separator)) :]

    @classmethod
    def _decoded_mapping(
        cls,
        entries: Iterable[tuple[str, str | bytes | None]],
    ) -> dict[str, Any]:
        """Decode backend key/value pairs into a logical registry mapping."""
        result: dict[str, Any] = {}
        for key, value in entries:
            if not value:
                continue
            decoded = cls._deserialize_value(key, value)
            if decoded is not None:
                result[key] = decoded
        return result

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

class PrefixedRegistryAdapter(RegistryAdapter):
    """Shared helpers for backends that store logical keys under a prefix."""

    prefix: str
    _prefix_separator = ""

    def _storage_key(self, key: str) -> str:
        return self._prefixed_key(self.prefix, key, self._prefix_separator)

    def _storage_prefix(self) -> str:
        return self._normalized_prefix(self.prefix, self._prefix_separator)

    def _logical_key(self, stored_key: str) -> str:
        return self._unprefixed_key(stored_key, self.prefix, self._prefix_separator)

class SerializedPrefixedRegistryAdapter(PrefixedRegistryAdapter):
    """Shared CRUD helpers for prefixed backends storing serialized values."""

    async def _set(self, key: str, value: Any) -> None:
        json_value = self._serialize_value(key, value)
        if json_value is None:
            return
        await self._write_storage_value(self._storage_key(key), json_value)
        await self._after_storage_write(key)
        self._log_backend_key_action("Set", key)

    async def _get(self, key: str) -> Any | None:
        value = await self._read_storage_value(self._storage_key(key))
        if value:
            return self._deserialize_value(key, value)
        return None

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        merged = self._merged_updated_value(await self._get(key), updates)
        json_value = self._serialize_value(key, merged)
        if json_value is None:
            return
        await self._write_storage_value(self._storage_key(key), json_value)
        await self._after_storage_write(key)
        self._log_backend_key_action("Updated", key)

    async def _delete(self, key: str) -> bool:
        storage_key = self._storage_key(key)
        if not await self._storage_key_exists(storage_key):
            return False
        await self._delete_storage_key(storage_key)
        await self._after_storage_delete(key)
        self._log_backend_key_action("Deleted", key)
        return True

    async def _exists(self, key: str) -> bool:
        return await self._storage_key_exists(self._storage_key(key))

    async def _get_all(self) -> dict[str, Any]:
        return self._decoded_mapping(await self._storage_entries())

    async def _clear(self) -> None:
        await self._clear_storage()
        self._log_backend_action("Cleared")

    async def _after_storage_write(self, key: str) -> None:
        return None

    async def _after_storage_delete(self, key: str) -> None:
        return None

    @abstractmethod
    async def _read_storage_value(self, storage_key: str) -> str | bytes | None:
        ...

    @abstractmethod
    async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
        ...

    @abstractmethod
    async def _storage_key_exists(self, storage_key: str) -> bool:
        ...

    @abstractmethod
    async def _delete_storage_key(self, storage_key: str) -> None:
        ...

    @abstractmethod
    async def _storage_entries(self) -> list[tuple[str, str | bytes | None]]:
        ...

    @abstractmethod
    async def _clear_storage(self) -> None:
        ...

__all__ = [
    "PrefixedRegistryAdapter",
    "RegistryAdapter",
    "SerializedPrefixedRegistryAdapter",
]
