"""Factory for creating registry adapters."""

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

# Backend definitions: (module_path, class_name, defaults, pip_extra, package_name)
_EXTERNAL_BACKENDS: dict[str, tuple[str, str, dict, str, str]] = {
    "redis": (
        "ofx.runner.registry.redis",
        "RedisJobRegistry",
        {"host": "localhost", "port": 6379, "db": 0, "password": None, "prefix": "ofx:job:"},
        "redis",
        "redis",
    ),
    "memcached": (
        "ofx.runner.registry.memcached",
        "MemcachedJobRegistry",
        {"host": "localhost", "port": 11211, "prefix": "ofx:job:"},
        "memcached",
        "aiomcache",
    ),
    "etcd": (
        "ofx.runner.registry.etcd",
        "EtcdJobRegistry",
        {"host": "localhost", "port": 2379, "prefix": "/ofx/job/"},
        "etcd",
        "etcd3",
    ),
}


class RegistryFactory:
    """Factory for creating registry adapters with caching and failover layers."""

    @staticmethod
    def _extract_config(config: BaseModel | dict | None, defaults: dict) -> dict:
        if config is None:
            return dict(defaults)
        if isinstance(config, dict):
            return {k: config.get(k, v) for k, v in defaults.items()}
        return {k: getattr(config, k, v) for k, v in defaults.items()}

    @staticmethod
    def _wrap(
        registry: RegistryAdapter,
        enable_cache: bool,
        cache_ttl: float,
        cache_max_entries: int,
        enable_failover: bool,
    ) -> RegistryAdapter:
        if enable_cache:
            registry = CachedRegistryAdapter(registry, ttl=cache_ttl, max_entries=cache_max_entries)
        if enable_failover and not isinstance(registry, (MemoryJobRegistry, FailoverRegistryAdapter)):
            registry = FailoverRegistryAdapter(registry)
        return registry

    @classmethod
    def _create_external(
        cls,
        backend: str,
        config: BaseModel | dict | None = None,
        *,
        enable_cache: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        enable_failover: bool = True,
        **kwargs: Any,
    ) -> RegistryAdapter:
        """Create an external (redis/memcached/etcd) registry backend."""
        mod_path, cls_name, defaults, pip_extra, pkg_name = _EXTERNAL_BACKENDS[backend]
        try:
            import importlib
            mod = importlib.import_module(mod_path)
            registry_cls = getattr(mod, cls_name)
        except ImportError as e:
            raise ImportError(
                f"{backend.title()} support requires the '{pkg_name}' package. "
                f"Install it with: pip install ofx[{pip_extra}]"
            ) from e

        params = cls._extract_config(config, defaults)
        params.update(kwargs)

        # Unwrap SecretStr password if present
        pw = params.get("password")
        if pw is not None and hasattr(pw, "get_secret_value"):
            params["password"] = pw.get_secret_value() or None
        if params.get("password") is None:
            params.pop("password", None)

        logger.debug("Creating %s with params: %s", cls_name, params)
        registry = registry_cls(**params)
        return cls._wrap(registry, enable_cache, cache_ttl, cache_max_entries, enable_failover)

    @classmethod
    def create(
        cls,
        backend: RegistryBackend = "memory",
        *,
        enable_cache: bool | None = None,
        enable_failover: bool = True,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        config: BaseModel | dict | None = None,
        **kwargs: Any,
    ) -> RegistryAdapter:
        """Create a registry adapter by backend type."""
        cache_flag = enable_cache if enable_cache is not None else backend != "memory"

        if backend == "memory":
            logger.debug("Creating MemoryJobRegistry")
            return cls._wrap(MemoryJobRegistry(), cache_flag, cache_ttl, cache_max_entries, False)

        if backend == "file":
            file_kwargs = {}
            if "filepath" in kwargs:
                file_kwargs["filepath"] = kwargs.pop("filepath")
            logger.debug("Creating FileRegistry with kwargs: %s", file_kwargs)
            registry = FileRegistry(**file_kwargs)
            return cls._wrap(registry, cache_flag, cache_ttl, cache_max_entries, enable_failover)

        if backend in _EXTERNAL_BACKENDS:
            return cls._create_external(
                backend,
                config=config,
                enable_cache=cache_flag,
                cache_ttl=cache_ttl,
                cache_max_entries=cache_max_entries,
                enable_failover=enable_failover,
                **kwargs,
            )

        raise ValueError(
            f"Unsupported registry backend: {backend}. "
            f"Supported: memory, file, redis, memcached, etcd"
        )

    @classmethod
    def create_from_settings(cls) -> RegistryAdapter:
        """Create a registry based on application settings."""
        backend = settings.registry_backend
        kwargs: dict[str, Any] = {}

        if backend == "file":
            kwargs["filepath"] = settings.registry_file_path
        elif backend in _EXTERNAL_BACKENDS:
            config_map = {"redis": "registry_redis", "memcached": "registry_memcached", "etcd": "registry_etcd"}
            kwargs["config"] = getattr(settings, config_map.get(backend, ""), None)

        try:
            registry = cls.create(
                backend,  # type: ignore[arg-type]
                enable_cache=settings.registry_cache_enabled,
                enable_failover=settings.registry_failover_enabled,
                cache_ttl=settings.registry_cache_ttl,
                cache_max_entries=settings.registry_cache_max_entries,
                **kwargs,
            )
            if backend not in ("memory",):
                logger.debug("Using %s registry backend", backend)
            return registry
        except Exception as exc:
            logger.warning(
                "Registry backend '%s' failed (%s). "
                "Falling back to in-memory registry — data will not persist across runs.",
                backend,
                exc,
            )
            return cls.create("memory", enable_cache=settings.registry_cache_enabled)


async def cleanup_registry(registry: RegistryAdapter) -> None:
    """Clean up registry resources."""
    try:
        await registry.close()
        logger.debug("Cleaned up %s", type(registry).__name__)
    except Exception as e:
        logger.error("Error cleaning up registry: %s", e)
