"""Factory for creating registry adapters"""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from ofx.runner.core.registries.base import RegistryAdapter
from ofx.runner.core.registries.file import FileJobRegistry
from ofx.runner.core.registries.memory import MemoryJobRegistry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

RegistryBackend = Literal["memory", "file", "redis", "memcached", "etcd"]


class RegistryFactory:
    """Factory class for creating registry adapters with cleaner config extraction"""

    @staticmethod
    def _extract_config(config: BaseModel | dict | None, defaults: dict) -> dict:
        """Extract configuration from BaseModel or dict with fallback to defaults

        Args:
            config: Configuration object (BaseModel, dict, or None)
            defaults: Default values to use if config is None

        Returns:
            Dictionary of configuration values
        """
        if config is None:
            return defaults

        if isinstance(config, dict):
            return {key: config.get(key, default) for key, default in defaults.items()}

        # BaseModel - use getattr
        return {key: getattr(config, key, default) for key, default in defaults.items()}

    @classmethod
    def create_memory(cls) -> RegistryAdapter:
        """Create in-memory registry"""
        logger.debug("Creating MemoryJobRegistry")
        return MemoryJobRegistry()

    @classmethod
    def create_file(cls, filepath: str | None = None) -> RegistryAdapter:
        """Create file-based registry

        Args:
            filepath: Path to registry file (optional)
        """
        kwargs = {}
        if filepath:
            kwargs["filepath"] = filepath
        logger.debug(f"Creating FileJobRegistry with kwargs: {kwargs}")
        return FileJobRegistry(**kwargs)

    @classmethod
    def create_redis(
        cls, config: BaseModel | dict | None = None, **kwargs
    ) -> RegistryAdapter:
        """Create Redis-based registry

        Args:
            config: Redis configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.core.registries.redis import RedisJobRegistry

            defaults = {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "password": None,
                "prefix": "ofx:job:",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            # Remove None password
            if params.get("password") is None:
                params.pop("password", None)

            logger.debug(f"Creating RedisJobRegistry with kwargs: {params}")
            return RedisJobRegistry(**params)
        except ImportError as e:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install it with: pip install ofx[redis]"
            ) from e

    @classmethod
    def create_memcached(
        cls, config: BaseModel | dict | None = None, **kwargs
    ) -> RegistryAdapter:
        """Create Memcached-based registry

        Args:
            config: Memcached configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.core.registries.memcached import MemcachedJobRegistry

            defaults = {
                "host": "localhost",
                "port": 11211,
                "prefix": "ofx:job:",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            logger.debug(f"Creating MemcachedJobRegistry with kwargs: {params}")
            return MemcachedJobRegistry(**params)
        except ImportError as e:
            raise ImportError(
                "Memcached support requires the 'aiomcache' package. "
                "Install it with: pip install ofx[memcached]"
            ) from e

    @classmethod
    def create_etcd(
        cls, config: BaseModel | dict | None = None, **kwargs
    ) -> RegistryAdapter:
        """Create etcd-based registry

        Args:
            config: etcd configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.core.registries.etcd import EtcdJobRegistry

            defaults = {
                "host": "localhost",
                "port": 2379,
                "prefix": "/ofx/job/",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            logger.debug(f"Creating EtcdJobRegistry with kwargs: {params}")
            return EtcdJobRegistry(**params)
        except ImportError as e:
            raise ImportError(
                "etcd support requires the 'etcd3' package. "
                "Install it with: pip install ofx[etcd]"
            ) from e

    @classmethod
    def create(
        cls, backend: RegistryBackend = "memory", **kwargs: Any
    ) -> RegistryAdapter:
        """Create a registry adapter based on backend type

        Args:
            backend: Type of registry backend
            **kwargs: Backend-specific configuration

        Returns:
            JobRegistryAdapter instance

        Raises:
            ValueError: If backend type is unsupported
        """
        if backend == "memory":
            return cls.create_memory()
        elif backend == "file":
            return cls.create_file(**kwargs)
        elif backend == "redis":
            return cls.create_redis(**kwargs)
        elif backend == "memcached":
            return cls.create_memcached(**kwargs)
        elif backend == "etcd":
            return cls.create_etcd(**kwargs)
        else:
            raise ValueError(
                f"Unsupported registry backend: {backend}. "
                f"Supported backends: memory, file, redis, memcached, etcd"
            )

    @classmethod
    def create_from_settings(cls) -> RegistryAdapter:
        """Create a registry based on application settings

        Returns:
            JobRegistryAdapter instance configured from settings
        """
        backend = settings.registry_backend

        if backend == "memory":
            return cls.create_memory()
        elif backend == "file":
            return cls.create_file(filepath=settings.registry_file_path)
        elif backend == "redis":
            return cls.create_redis(config=settings.registry_redis)
        elif backend == "memcached":
            return cls.create_memcached(config=settings.registry_memcached)
        elif backend == "etcd":
            return cls.create_etcd(config=settings.registry_etcd)
        else:
            logger.warning(
                f"Unknown registry backend '{backend}', falling back to memory registry"
            )
            return cls.create_memory()


async def cleanup_registry(registry: RegistryAdapter) -> None:
    """Clean up registry resources

    Args:
        registry: JobRegistryAdapter instance to clean up
    """
    try:
        await registry.close()
        logger.debug(f"Cleaned up {type(registry).__name__}")
    except Exception as e:
        logger.error(f"Error cleaning up registry: {e}")
