"""etcd-based registry adapter for distributed coordination"""

import json
import logging
from typing import Any

from ofx.runner.registry.base import RegistryAdapter

try:
    import etcd3

    ETCD_AVAILABLE = True
except ImportError:
    ETCD_AVAILABLE = False
    etcd3 = None  # type: ignore

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class EtcdJobRegistry(RegistryAdapter):
    """etcd-based implementation of registry

    Stores data in etcd for distributed coordination and strong consistency.
    Requires the 'etcd3' package to be installed (optional dependency).

    etcd provides:
    - Strong consistency guarantees
    - Persistent storage
    - Distributed coordination
    - Watch capabilities
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2379,
        prefix: str = "/ofx/job/",
        timeout: int = 5,
        **kwargs,
    ):
        """Initialize the etcd-based registry

        Args:
            host: etcd server host
            port: etcd server port (default gRPC port)
            prefix: Key prefix for all registry entries
            timeout: Connection timeout in seconds
            **kwargs: Additional etcd3 client arguments
        """
        if not ETCD_AVAILABLE:
            raise ImportError(
                "etcd support requires the 'etcd3' package. "
                "Install it with: pip install ofx[etcd]"
            )

        self.prefix = prefix
        self._client = etcd3.client(
            host=host,
            port=port,
            timeout=timeout,
            **kwargs,
        )
        self._log_debug(f"Initialized EtcdJobRegistry at {host}:{port}")

    def _make_key(self, key: str) -> str:
        """Create an etcd key for a data identifier

        Args:
            key: Data identifier

        Returns:
            etcd key with prefix
        """
        # Ensure prefix ends with / for proper path-like structure
        prefix = self.prefix if self.prefix.endswith("/") else f"{self.prefix}/"
        return f"{prefix}{key}"

    async def _set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in etcd"""
        etcd_key = self._make_key(key)
        json_value = json.dumps(value)
        self._client.put(etcd_key, json_value)
        self._log_debug(f"Set key '{key}' in EtcdJobRegistry")

    async def _get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from etcd"""
        etcd_key = self._make_key(key)
        value, _ = self._client.get(etcd_key)
        if value:
            return json.loads(value.decode())
        return None

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data"""
        existing = await self._get(key)
        if existing is not None:
            existing.update(updates)
            await self._set(key, existing)
        else:
            await self._set(key, updates)
        self._log_debug(f"Updated key '{key}' in EtcdJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from etcd"""
        etcd_key = self._make_key(key)

        # Check if key exists first
        value, _ = self._client.get(etcd_key)
        if value:
            self._client.delete(etcd_key)
            self._log_debug(f"Deleted key '{key}' from EtcdJobRegistry")
            return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in etcd"""
        etcd_key = self._make_key(key)
        value, _ = self._client.get(etcd_key)
        return value is not None

    async def _get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from etcd"""
        # Get all keys with the prefix
        result = {}
        prefix = self.prefix if self.prefix.endswith("/") else f"{self.prefix}/"

        for value, metadata in self._client.get_prefix(prefix):
            if value:
                # Extract the key from the full etcd key
                etcd_key = metadata.key.decode()
                key = etcd_key[len(prefix) :]
                result[key] = json.loads(value.decode())

        return result

    async def _clear(self) -> None:
        """Clear all entries from etcd"""
        prefix = self.prefix if self.prefix.endswith("/") else f"{self.prefix}/"
        self._client.delete_prefix(prefix)
        self._log_debug("Cleared EtcdJobRegistry")

    async def _close(self) -> None:
        """Close the etcd connection"""
        if self._client:
            self._client.close()
            self._client = None
        self._log_debug("Closed EtcdJobRegistry")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)
