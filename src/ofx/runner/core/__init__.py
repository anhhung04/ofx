"""Core runner components"""

from ofx.runner.core.base import BaseRunner
from ofx.runner.core.models import RunContext, RunnerStatus, RunResult
from ofx.runner.core.registries import (
    FileJobRegistry,
    JobRegistryAdapter,
    MemoryJobRegistry,
)
from ofx.runner.core.registries.factory import (
    RegistryFactory,
    cleanup_registry,
)

__all__ = [
    "BaseRunner",
    "RunContext",
    "RunnerStatus",
    "RunResult",
    "JobRegistryAdapter",
    "MemoryJobRegistry",
    "FileJobRegistry",
    "RegistryFactory",
    "cleanup_registry",
]

# Conditionally export RedisJobRegistry if available
try:
    from ofx.runner.core.registries import RedisJobRegistry

    __all__.append("RedisJobRegistry")
except ImportError:
    pass
