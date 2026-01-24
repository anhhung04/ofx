"""Job registry adapters using the adapter pattern"""

from ofx.runner.core.registries.base import RegistryAdapter
from ofx.runner.core.registries.factory import (
    RegistryFactory,
    cleanup_registry,
)
from ofx.runner.core.registries.file import FileJobRegistry
from ofx.runner.core.registries.memory import MemoryJobRegistry

__all__ = [
    "RegistryAdapter",
    "MemoryJobRegistry",
    "FileJobRegistry",
    "RegistryFactory",
    "cleanup_registry",
]

try:
    from ofx.runner.core.registries.redis import RedisJobRegistry

    __all__.append("RedisJobRegistry")
except ImportError:
    pass

try:
    from ofx.runner.core.registries.memcached import MemcachedJobRegistry

    __all__.append("MemcachedJobRegistry")
except ImportError:
    pass

try:
    from ofx.runner.core.registries.etcd import EtcdJobRegistry

    __all__.append("EtcdJobRegistry")
except ImportError:
    pass
