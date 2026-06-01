"""Unified registry adapter interface and backend factory."""

from __future__ import annotations

import logging
from typing import Any

from ofx.runner.registry_adapter import RegistryAdapter
from ofx.runner.registry_backends import (
    EtcdJobRegistry,
    FileRegistry,
    MemcachedJobRegistry,
    MemoryJobRegistry,
    RedisJobRegistry,
)
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

DEFAULT_BACKEND_MAP: dict[str, type[RegistryAdapter]] = {
    "memory": MemoryJobRegistry,
    "file": FileRegistry,
    "redis": RedisJobRegistry,
    "etcd": EtcdJobRegistry,
    "memcached": MemcachedJobRegistry,
}


def _registry_type_name(registry: RegistryAdapter) -> str:
    return type(registry).__name__


def _normalize_registry_password(config: dict[str, Any]) -> None:
    if "password" not in config:
        return

    password = config["password"]
    if hasattr(password, "get_secret_value"):
        password = password.get_secret_value() or None
    if password is None:
        config.pop("password")
    else:
        config["password"] = password


class RegistryFactory:
    """Declarative factory for creating registry adapters."""

    _backends: dict[str, type[RegistryAdapter]] = dict(DEFAULT_BACKEND_MAP)

    @classmethod
    def register(cls, name: str, backend_cls: type[RegistryAdapter]) -> None:
        """Register a registry backend class under a backend name."""
        cls._backends[name] = backend_cls

    @classmethod
    def supported_backends(cls) -> tuple[str, ...]:
        """Return the supported backend names."""
        return tuple(cls._backends)

    @classmethod
    def create(cls, backend: str = "memory", **config: Any) -> RegistryAdapter:
        """Create a registry adapter for the requested backend."""
        try:
            backend_cls = cls._backends[backend]
        except KeyError as exc:
            supported = ", ".join(sorted(cls._backends))
            raise ValueError(
                f"Unsupported registry backend: {backend}. Supported: {supported}"
            ) from exc

        config = dict(config)
        _normalize_registry_password(config)

        logger.debug("Creating %s with config: %s", backend_cls.__name__, config)
        return backend_cls(**config)


async def cleanup_registry(registry: RegistryAdapter) -> None:
    """Clean up registry resources."""
    try:
        await registry.close()
        logger.debug("Cleaned up %s", _registry_type_name(registry))
    except Exception as exc:
        logger.error("Error cleaning up %s: %s", _registry_type_name(registry), exc)


__all__ = [
    "DEFAULT_BACKEND_MAP",
    "EtcdJobRegistry",
    "FileRegistry",
    "MemcachedJobRegistry",
    "MemoryJobRegistry",
    "RegistryAdapter",
    "RegistryFactory",
    "RedisJobRegistry",
    "cleanup_registry",
]
