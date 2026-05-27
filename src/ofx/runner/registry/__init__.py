"""Compatibility exports for registry adapters.

Canonical backend implementations live under `ofx.runner.registry_backends`.
Importing through `ofx.runner.registry` continues to work for backward
compatibility.
"""

from __future__ import annotations

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.cache import CachedRegistryAdapter
from ofx.runner.registry.factory import RegistryFactory, cleanup_registry
from ofx.runner.registry.failover import FailoverRegistryAdapter
from ofx.runner.registry_backends.file import FileRegistry
from ofx.runner.registry_backends.memory import MemoryJobRegistry, RegistryOverflowError

__all__ = [
    "RegistryAdapter",
    "MemoryJobRegistry",
    "RegistryOverflowError",
    "FileRegistry",
    "CachedRegistryAdapter",
    "FailoverRegistryAdapter",
    "RegistryFactory",
    "cleanup_registry",
]


try:
    from ofx.runner.registry_backends.redis import RedisJobRegistry

    __all__.append("RedisJobRegistry")
except ImportError:
    pass


def __getattr__(name: str):
    if name == "MemcachedJobRegistry":
        import warnings
        from ofx.runner.registry_backends.memcached import MemcachedJobRegistry

        warnings.warn(
            "Importing MemcachedJobRegistry from 'ofx.runner.registry' is deprecated. "
            "Import it from 'ofx.runner.registry_backends.memcached' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return MemcachedJobRegistry
    if name == "EtcdJobRegistry":
        import warnings
        from ofx.runner.registry_backends.etcd import EtcdJobRegistry

        warnings.warn(
            "Importing EtcdJobRegistry from 'ofx.runner.registry' is deprecated. "
            "Import it from 'ofx.runner.registry_backends.etcd' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return EtcdJobRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
