"""Memcached-based registry adapter for distributed caching"""

import logging
import warnings
from typing import Any

from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter

try:
    import aiomcache

    MEMCACHED_AVAILABLE = True
except ImportError:
    MEMCACHED_AVAILABLE = False
    aiomcache = None

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

class MemcachedJobRegistry(SerializedPrefixedRegistryAdapter):
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
        warnings.warn(
            "MemcachedJobRegistry is deprecated and may be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
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
        self._log_backend_initialized(f"at {host}:{port}")

    async def _get_client(self):
        """Get or create the Memcached client"""
        if self._client is None:
            client_cls = aiomcache.Client
            self._client = client_cls(self.host, self.port)
        return self._client

    def _make_index_key(self) -> str:
        """Create the index key that stores all registry keys"""
        return f"{self.prefix}_index"

    def _cache_key_bytes(self, key: str) -> bytes:
        return self._storage_key(key).encode()

    def _index_key_bytes(self) -> bytes:
        return self._make_index_key().encode()

    async def _get_cached_bytes(self, client, key: str) -> bytes | None:
        return await client.get(self._cache_key_bytes(key))

    async def _set_cached_json(self, client, key: str, json_value: str) -> None:
        await client.set(self._cache_key_bytes(key), json_value.encode())

    async def _delete_cached_key(self, client, key: str) -> None:
        await client.delete(self._cache_key_bytes(key))

    async def _get_index(self) -> list[str]:
        """Load the index of registry keys from Memcached."""
        client = await self._get_client()
        index_key = self._make_index_key()
        index_data = await client.get(self._index_key_bytes())
        if not index_data:
            return []

        decoded = self._deserialize_value(index_key, index_data)
        if isinstance(decoded, list):
            return decoded
        return []

    async def _set_index(self, keys: list[str]) -> None:
        """Persist the index of registry keys to Memcached."""
        client = await self._get_client()
        index_key = self._make_index_key()
        json_value = self._serialize_value(index_key, keys)
        if json_value is not None:
            await client.set(self._index_key_bytes(), json_value.encode())

    async def _add_to_index(self, key: str) -> None:
        """Add a key to the index of all keys"""
        try:
            keys = await self._get_index()
        except Exception as exc:
            logger.warning("Failed to fetch memcached index: %s", exc)
            keys = []

        if key not in keys:
            keys.append(key)
            await self._set_index(keys)

    async def _remove_from_index(self, key: str) -> None:
        """Remove a key from the index of all keys"""
        try:
            keys = await self._get_index()
            if key in keys:
                keys.remove(key)
                await self._set_index(keys)
        except Exception as e:
            logger.warning("Memcached delete failed for key removal: %s", e)

    async def _read_storage_value(self, storage_key: str) -> str | bytes | None:
        client = await self._get_client()
        return await client.get(storage_key.encode())

    async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
        client = await self._get_client()
        await client.set(storage_key.encode(), json_value.encode())

    async def _storage_key_exists(self, storage_key: str) -> bool:
        return await self._read_storage_value(storage_key) is not None

    async def _delete_storage_key(self, storage_key: str) -> None:
        client = await self._get_client()
        await client.delete(storage_key.encode())

    async def _after_storage_write(self, key: str) -> None:
        await self._add_to_index(key)

    async def _after_storage_delete(self, key: str) -> None:
        await self._remove_from_index(key)

    async def _storage_entries(self) -> list[tuple[str, str | bytes | None]]:
        client = await self._get_client()
        try:
            return [
                (key, await self._get_cached_bytes(client, key))
                for key in await self._get_index()
            ]
        except Exception as e:
            logger.warning("Memcached get_all failed: %s", e)
            return []

    async def _clear_storage(self) -> None:
        client = await self._get_client()

        try:
            for key in await self._get_index():
                await self._delete_cached_key(client, key)

            await client.delete(self._index_key_bytes())
        except Exception as e:
            logger.warning("Memcached clear failed: %s", e)

    async def _close(self) -> None:
        """Close the Memcached connection"""
        if self._client:
            await self._client.close()
            self._client = None
        self._log_backend_action("Closed")
