"""Redis-based registry adapter for distributed storage"""

import json
import logging
from typing import Any

from ofx.runner.core.registries.base import JobRegistryAdapter

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    Redis = None  # type: ignore

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class RedisJobRegistry(JobRegistryAdapter):
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
        logger.debug(f"Initialized RedisJobRegistry at {host}:{port}/{db}")

    def _make_key(self, key: str) -> str:
        """Create a Redis key for a data identifier

        Args:
            key: Data identifier

        Returns:
            Redis key with prefix
        """
        return f"{self.prefix}{key}"

    async def set(self, key: str, value: dict[str, Any]) -> None:
        """Store data in Redis

        Args:
            key: Unique identifier for the data
            value: Data to store (must be JSON-serializable)
        """
        redis_key = self._make_key(key)
        json_value = json.dumps(value)
        await self._client.set(redis_key, json_value)
        logger.debug(f"Set key '{key}' in RedisJobRegistry")

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve data from Redis

        Args:
            key: Unique identifier for the data

        Returns:
            Data if found, None otherwise
        """
        redis_key = self._make_key(key)
        value = await self._client.get(redis_key)
        if value:
            return json.loads(value)
        return None

    async def update(self, key: str, updates: dict[str, Any]) -> None:
        """Update specific fields in data

        Args:
            key: Unique identifier for the data
            updates: Fields to update in the data
        """
        existing = await self.get(key)
        if existing:
            existing.update(updates)
            await self.set(key, existing)
            logger.debug(f"Updated key '{key}' in RedisJobRegistry")
        else:
            logger.warning(f"Cannot update key '{key}' - not found in RedisJobRegistry")

    async def delete(self, key: str) -> bool:
        """Remove data from Redis

        Args:
            key: Unique identifier for the data

        Returns:
            True if deleted, False if not found
        """
        redis_key = self._make_key(key)
        deleted = await self._client.delete(redis_key)
        if deleted:
            logger.debug(f"Deleted key '{key}' from RedisJobRegistry")
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check if data exists in Redis

        Args:
            key: Unique identifier for the data

        Returns:
            True if data exists, False otherwise
        """
        redis_key = self._make_key(key)
        return bool(await self._client.exists(redis_key))

    async def get_all(self) -> dict[str, dict[str, Any]]:
        """Get all entries from Redis

        Returns:
            Dictionary mapping keys to their data
        """
        pattern = f"{self.prefix}*"
        keys = await self._client.keys(pattern)

        result = {}
        for redis_key in keys:
            key = redis_key[len(self.prefix) :]
            value = await self._client.get(redis_key)
            if value:
                result[key] = json.loads(value)

        return result

    async def clear(self) -> None:
        """Clear all entries from Redis"""
        pattern = f"{self.prefix}*"
        keys = await self._client.keys(pattern)
        if keys:
            await self._client.delete(*keys)
        logger.debug("Cleared RedisJobRegistry")

    async def close(self) -> None:
        """Close the Redis connection"""
        await self._client.close()
        logger.debug("Closed RedisJobRegistry")
