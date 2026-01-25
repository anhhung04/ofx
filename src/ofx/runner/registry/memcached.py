"""Memcached-based registry adapter for distributed caching"""

import json
import logging
from typing import Any

from ofx.runner.registry.base import RegistryAdapter

try:
    import aiomcache

    MEMCACHED_AVAILABLE = True
except ImportError:
    MEMCACHED_AVAILABLE = False
    aiomcache = None  # type: ignore

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class MemcachedJobRegistry(RegistryAdapter):
    """Memcached-based implementation of registry

    Stores data in Memcached for distributed caching and high-performance access.
    Requires the 'aiomcache' package to be installed (optional dependency).

    Note: Memcached is volatile storage - data is lost on restart.
    Use for caching and high-speed temporary storage.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11211,
        prefix: str = "ofx:job:",
        pool_size: int = 2,
        pool_minsize: int = 1,
        **kwargs,
    ):
        """Initialize the Memcached-based registry

        Args:
            host: Memcached server host
            port: Memcached server port
            prefix: Key prefix for all registry entries
            pool_size: Maximum number of connections in the pool
            pool_minsize: Minimum number of connections in the pool
            **kwargs: Additional client arguments
        """
        if not MEMCACHED_AVAILABLE:
            raise ImportError(
                "Memcached support requires the 'aiomcache' package. "
                "Install it with: pip install ofx[memcached]"
            )

        self.prefix = prefix
        self.host = host
        self.port = port
        self._client = None
        self._pool_size = pool_size
        self._pool_minsize = pool_minsize
        self._log_debug(f"Initialized MemcachedJobRegistry at {host}:{port}")

    async def _get_client(self):
        """Get or create the Memcached client"""
        if self._client is None:
            self._client = aiomcache.Client(self.host, self.port)
        return self._client

    def _make_key(self, key: str) -> str:
        """Create a Memcached key for a data identifier

        Args:
            key: Data identifier

        Returns:
            Memcached key with prefix
        """
        return f"{self.prefix}{key}"

    def _make_index_key(self) -> str:
        """Create the index key that stores all registry keys"""
        return f"{self.prefix}_index"

    async def _add_to_index(self, key: str) -> None:
        """Add a key to the index of all keys"""
        client = await self._get_client()
        index_key = self._make_index_key()

        try:
            index_data = await client.get(index_key.encode())
            if index_data:
                keys = json.loads(index_data.decode())
            else:
                keys = []
        except Exception:
            keys = []

        if key not in keys:
            keys.append(key)
            await client.set(index_key.encode(), json.dumps(keys).encode())

    async def _remove_from_index(self, key: str) -> None:
        """Remove a key from the index of all keys"""
        client = await self._get_client()
        index_key = self._make_index_key()

        try:
            index_data = await client.get(index_key.encode())
            if index_data:
                keys = json.loads(index_data.decode())
                if key in keys:
                    keys.remove(key)
                    await client.set(index_key.encode(), json.dumps(keys).encode())
        except Exception:
            pass

    async def _set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in Memcached"""
        client = await self._get_client()
        cache_key = self._make_key(key)
        json_value = json.dumps(value)
        await client.set(cache_key.encode(), json_value.encode())
        await self._add_to_index(key)
        self._log_debug(f"Set key '{key}' in MemcachedJobRegistry")

    async def _get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from Memcached"""
        client = await self._get_client()
        cache_key = self._make_key(key)
        value = await client.get(cache_key.encode())
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
        self._log_debug(f"Updated key '{key}' in MemcachedJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from Memcached"""
        client = await self._get_client()
        cache_key = self._make_key(key)

        # Check if key exists first
        exists = await client.get(cache_key.encode())
        if exists:
            await client.delete(cache_key.encode())
            await self._remove_from_index(key)
            self._log_debug(f"Deleted key '{key}' from MemcachedJobRegistry")
            return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in Memcached"""
        client = await self._get_client()
        cache_key = self._make_key(key)
        value = await client.get(cache_key.encode())
        return value is not None

    async def _get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from Memcached"""
        client = await self._get_client()
        index_key = self._make_index_key()

        try:
            index_data = await client.get(index_key.encode())
            if not index_data:
                return {}

            keys = json.loads(index_data.decode())
            result = {}

            for key in keys:
                cache_key = self._make_key(key)
                value = await client.get(cache_key.encode())
                if value:
                    result[key] = json.loads(value.decode())

            return result
        except Exception:
            return {}

    async def _clear(self) -> None:
        """Clear all entries from Memcached"""
        client = await self._get_client()
        index_key = self._make_index_key()

        try:
            index_data = await client.get(index_key.encode())
            if index_data:
                keys = json.loads(index_data.decode())
                for key in keys:
                    cache_key = self._make_key(key)
                    await client.delete(cache_key.encode())

                # Clear the index itself
                await client.delete(index_key.encode())
        except Exception:
            pass

        self._log_debug("Cleared MemcachedJobRegistry")

    async def _close(self) -> None:
        """Close the Memcached connection"""
        if self._client:
            await self._client.close()
            self._client = None
        self._log_debug("Closed MemcachedJobRegistry")

    @staticmethod
    def _log_debug(message: str) -> None:
        logger.debug(message)
