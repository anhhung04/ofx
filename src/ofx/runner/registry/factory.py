"""Factory for creating registry adapters"""

import logging
from typing import Any, Literal

from pydantic import BaseModel

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.cache import CachedRegistryAdapter
from ofx.runner.registry.failover import FailoverRegistryAdapter
from ofx.runner.registry.file import FileRegistry
from ofx.runner.registry.memory import MemoryJobRegistry
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

RegistryBackend = Literal["memory", "file", "redis", "memcached", "etcd"]

DEFAULT_CACHE_TTL = 0.25
DEFAULT_CACHE_MAX_ENTRIES = 1024


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

    @staticmethod
    def _wrap_cache(
        registry: RegistryAdapter,
        enable_cache: bool,
        cache_ttl: float,
        cache_max_entries: int,
    ) -> RegistryAdapter:
        if not enable_cache:
            return registry
        return CachedRegistryAdapter(
            registry, ttl=cache_ttl, max_entries=cache_max_entries
        )

    @staticmethod
    def _wrap_failover(
        registry: RegistryAdapter,
        enable_failover: bool,
    ) -> RegistryAdapter:
        if not enable_failover:
            return registry
        from ofx.runner.registry.failover import FailoverRegistryAdapter as FRA

        if isinstance(registry, (MemoryJobRegistry, FRA)):
            return registry
        return FailoverRegistryAdapter(registry)

    @classmethod
    def create_memory(
        cls,
        *,
        enable_cache: bool = False,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool | None = None,
    ) -> RegistryAdapter:
        """Create in-memory registry"""
        _log_debug("Creating MemoryJobRegistry")
        registry = MemoryJobRegistry()
        return cls._wrap_cache(registry, enable_cache, cache_ttl, cache_max_entries)

    @classmethod
    def create_file(
        cls,
        filepath: str | None = None,
        *,
        enable_cache: bool = False,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool = False,
    ) -> RegistryAdapter:
        """Create file-based registry

        Args:
            filepath: Path to registry file (optional)
        """
        kwargs = {}
        if filepath:
            kwargs["filepath"] = filepath
        _log_debug(f"Creating FileJobRegistry with kwargs: {kwargs}")
        registry = FileRegistry(**kwargs)
        registry = cls._wrap_cache(registry, enable_cache, cache_ttl, cache_max_entries)
        return cls._wrap_failover(registry, enable_failover)

    @classmethod
    def create_redis(
        cls,
        config: BaseModel | dict | None = None,
        *,
        enable_cache: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool = True,
        **kwargs,
    ) -> RegistryAdapter:
        """Create Redis-based registry

        Args:
            config: Redis configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.registry.redis import RedisJobRegistry

            defaults = {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "password": None,
                "prefix": "ofx:job:",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            # Unwrap SecretStr password to plain string for the Redis client
            pw = params.get("password")
            if pw is not None and hasattr(pw, "get_secret_value"):
                params["password"] = pw.get_secret_value() or None

            # Remove None password
            if params.get("password") is None:
                params.pop("password", None)

            _log_debug(f"Creating RedisJobRegistry with kwargs: {params}")
            registry = RedisJobRegistry(**params)
            registry = cls._wrap_cache(
                registry, enable_cache, cache_ttl, cache_max_entries
            )
            return cls._wrap_failover(registry, enable_failover)
        except ImportError as e:
            raise ImportError(
                "Redis support requires the 'redis' package. "
                "Install it with: pip install ofx[redis]"
            ) from e

    @classmethod
    def create_memcached(
        cls,
        config: BaseModel | dict | None = None,
        *,
        enable_cache: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool = True,
        **kwargs,
    ) -> RegistryAdapter:
        """Create Memcached-based registry

        Args:
            config: Memcached configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.registry.memcached import MemcachedJobRegistry

            defaults = {
                "host": "localhost",
                "port": 11211,
                "prefix": "ofx:job:",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            _log_debug(f"Creating MemcachedJobRegistry with kwargs: {params}")
            registry = MemcachedJobRegistry(**params)
            registry = cls._wrap_cache(
                registry, enable_cache, cache_ttl, cache_max_entries
            )
            return cls._wrap_failover(registry, enable_failover)
        except ImportError as e:
            raise ImportError(
                "Memcached support requires the 'aiomcache' package. "
                "Install it with: pip install ofx[memcached]"
            ) from e

    @classmethod
    def create_etcd(
        cls,
        config: BaseModel | dict | None = None,
        *,
        enable_cache: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool = True,
        **kwargs,
    ) -> RegistryAdapter:
        """Create etcd-based registry

        Args:
            config: etcd configuration object or dict
            **kwargs: Override configuration values
        """
        try:
            from ofx.runner.registry.etcd import EtcdJobRegistry

            defaults = {
                "host": "localhost",
                "port": 2379,
                "prefix": "/ofx/job/",
            }

            params = cls._extract_config(config, defaults)
            params.update(kwargs)

            _log_debug(f"Creating EtcdJobRegistry with kwargs: {params}")
            registry = EtcdJobRegistry(**params)
            registry = cls._wrap_cache(
                registry, enable_cache, cache_ttl, cache_max_entries
            )
            return cls._wrap_failover(registry, enable_failover)
        except ImportError as e:
            raise ImportError(
                "etcd support requires the 'etcd3' package. "
                "Install it with: pip install ofx[etcd]"
            ) from e

    @classmethod
    def create(
        cls,
        backend: RegistryBackend = "memory",
        *,
        enable_cache: bool | None = None,
        enable_failover: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        **kwargs: Any,
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
        cache_flag = enable_cache if enable_cache is not None else backend != "memory"
        failover_flag = enable_failover

        if backend == "memory":
            return cls.create_memory(
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
            )
        elif backend == "file":
            registry = cls.create_file(
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                **kwargs,
            )
            return cls._wrap_failover(registry, failover_flag)
        elif backend == "redis":
            registry = cls.create_redis(
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                **kwargs,
            )
            return cls._wrap_failover(registry, failover_flag)
        elif backend == "memcached":
            registry = cls.create_memcached(
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                **kwargs,
            )
            return cls._wrap_failover(registry, failover_flag)
        elif backend == "etcd":
            registry = cls.create_etcd(
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                **kwargs,
            )
            return cls._wrap_failover(registry, failover_flag)
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
        cache_enabled = settings.registry_cache_enabled
        cache_ttl = settings.registry_cache_ttl
        cache_max_entries = settings.registry_cache_max_entries
        failover_enabled = settings.registry_failover_enabled

        if backend == "memory":
            return cls.create_memory(
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
            )
        elif backend == "file":
            return cls.create_file(
                filepath=settings.registry_file_path,
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                enable_failover=failover_enabled,
            )
        elif backend == "redis":
            return cls.create_redis(
                config=settings.registry_redis,
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                enable_failover=failover_enabled,
            )
        elif backend == "memcached":
            return cls.create_memcached(
                config=settings.registry_memcached,
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                enable_failover=failover_enabled,
            )
        elif backend == "etcd":
            return cls.create_etcd(
                config=settings.registry_etcd,
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                enable_failover=failover_enabled,
            )
        else:
            logger.warning(
                f"Unknown registry backend '{backend}', falling back to memory registry"
            )
            return cls.create_memory(
                enable_cache=cache_enabled,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
            )


async def cleanup_registry(registry: RegistryAdapter) -> None:
    """Clean up registry resources

    Args:
        registry: JobRegistryAdapter instance to clean up
    """
    try:
        await registry.close()
        _log_debug(f"Cleaned up {type(registry).__name__}")
    except Exception as e:
        logger.error(f"Error cleaning up registry: {e}")


def _log_debug(message: str) -> None:
    logger.debug(message)
