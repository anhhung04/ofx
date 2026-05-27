"""Registry backend implementations.

This package hosts concrete backend adapters that were historically exposed
from `ofx.runner.registry`. Importing through `ofx.runner.registry` continues
to work for backward compatibility.
"""

from ofx.runner.registry_backends.etcd import EtcdJobRegistry
from ofx.runner.registry_backends.file import FileRegistry
from ofx.runner.registry_backends.memcached import MemcachedJobRegistry
from ofx.runner.registry_backends.memory import MemoryJobRegistry, RegistryOverflowError
from ofx.runner.registry_backends.redis import RedisJobRegistry

__all__ = [
    "EtcdJobRegistry",
    "FileRegistry",
    "MemcachedJobRegistry",
    "MemoryJobRegistry",
    "RedisJobRegistry",
    "RegistryOverflowError",
]
