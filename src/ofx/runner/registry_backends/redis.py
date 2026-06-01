"""Redis-based registry adapter for distributed storage"""

from typing import Any

from ofx.runner.registry_adapter import SerializedPrefixedRegistryAdapter

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore

class RedisJobRegistry(SerializedPrefixedRegistryAdapter):
    """Redis-based implementation of registry

    Stores data in Redis for distributed access and persistence.
    Requires the 'redis' package to be installed (optional dependency).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        prefix: str = "ofx:job:",
        **kwargs,
    ):
        """Initialize the Redis-based registry

        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            password: Redis password (if required)
            prefix: Key prefix for all registry entries
            **kwargs: Additional Redis client arguments
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install it with: pip install ofx[redis]"
            )

        self.prefix = prefix
        self._client: Redis = aioredis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            **kwargs,
        )
        self._log_backend_initialized(f"at {host}:{port}/{db}")

    async def _read_storage_value(self, storage_key: str) -> str | bytes | None:
        return await self._client.get(storage_key)

    async def _write_storage_value(self, storage_key: str, json_value: str) -> None:
        await self._client.set(storage_key, json_value)

    async def _storage_key_exists(self, storage_key: str) -> bool:
        return bool(await self._client.exists(storage_key))

    async def _delete_storage_key(self, storage_key: str) -> None:
        await self._client.delete(storage_key)

    async def _storage_entries(self) -> list[tuple[str, str | bytes | None]]:
        pattern = f"{self._storage_prefix()}*"
        keys = await self._client.keys(pattern)
        return [
            (self._logical_key(redis_key), await self._client.get(redis_key))
            for redis_key in keys
        ]

    async def _clear_storage(self) -> None:
        pattern = f"{self._storage_prefix()}*"
        keys = await self._client.keys(pattern)
        if keys:
            await self._client.delete(*keys)

    async def _close(self) -> None:
        """Close the Redis connection"""
        await self._client.close()
        self._log_backend_action("Closed")
