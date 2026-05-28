"""Redis-based registry adapter for distributed storage"""

from typing import Any

from ofx.runner.registry_adapter import RegistryAdapter

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore

class RedisJobRegistry(RegistryAdapter):
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
        self._log_debug(f"Initialized RedisJobRegistry at {host}:{port}/{db}")

    def _make_key(self, key: str) -> str:
        """Create a Redis key for a data identifier

        Args:
            key: Data identifier

        Returns:
            Redis key with prefix
        """
        return f"{self.prefix}{key}"

    async def _set(self, key: str, value: Any) -> None:
        """Store data in Redis"""
        redis_key = self._make_key(key)
        json_value = self._serialize_value(key, value)
        if json_value is None:
            return
        await self._client.set(redis_key, json_value)
        self._log_debug(f"Set key '{key}' in RedisJobRegistry")

    async def _get(self, key: str) -> Any | None:
        """Retrieve data from Redis"""
        redis_key = self._make_key(key)
        value = await self._client.get(redis_key)
        if value:
            return self._deserialize_value(key, value)
        return None

    async def _update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data"""
        existing = await self._get(key)
        if isinstance(existing, dict):
            existing.update(updates)
            await self._set(key, existing)
        else:
            await self._set(key, updates)
        self._log_debug(f"Updated key '{key}' in RedisJobRegistry")

    async def _delete(self, key: str) -> bool:
        """Remove data from Redis"""
        redis_key = self._make_key(key)
        deleted = await self._client.delete(redis_key)
        if deleted:
            self._log_debug(f"Deleted key '{key}' from RedisJobRegistry")
            return True
        return False

    async def _exists(self, key: str) -> bool:
        """Check if data exists in Redis"""
        redis_key = self._make_key(key)
        return bool(await self._client.exists(redis_key))

    async def _get_all(self) -> dict[str, Any]:
        """Get all entries from Redis"""
        pattern = f"{self.prefix}*"
        keys = await self._client.keys(pattern)

        result = {}
        for redis_key in keys:
            key = redis_key[len(self.prefix) :]
            value = await self._client.get(redis_key)
            if value:
                decoded = self._deserialize_value(key, value)
                if decoded is not None:
                    result[key] = decoded

        return result

    async def _clear(self) -> None:
        """Clear all entries from Redis"""
        pattern = f"{self.prefix}*"
        keys = await self._client.keys(pattern)
        if keys:
            await self._client.delete(*keys)
        self._log_debug("Cleared RedisJobRegistry")

    async def _close(self) -> None:
        """Close the Redis connection"""
        await self._client.close()
        self._log_debug("Closed RedisJobRegistry")
