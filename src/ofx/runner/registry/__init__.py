"""Job registry adapters using the adapter pattern"""

from ofx.runner.registry.base import RegistryAdapter
from ofx.runner.registry.factory import (
    RegistryFactory,
    cleanup_registry,
)
from ofx.runner.registry.file import FileRegistry
from ofx.runner.registry.memory import MemoryJobRegistry

__all__ = [
    "RegistryAdapter",
    "MemoryJobRegistry",
    "FileRegistry",
    "RegistryFactory",
    "cleanup_registry",
]

try:
    from ofx.runner.registry.redis import RedisJobRegistry

    __all__.append("RedisJobRegistry")
except ImportError:
    pass

try:
    from ofx.runner.registry.memcached import MemcachedJobRegistry

    __all__.append("MemcachedJobRegistry")
except ImportError:
    pass

try:
    from ofx.runner.registry.etcd import EtcdJobRegistry

    __all__.append("EtcdJobRegistry")
except Exception:
    # etcd3 can fail at import-time due to protobuf version incompatibilities.
    # Keep registry importable; the backend can be enabled by fixing env deps.
    pass
