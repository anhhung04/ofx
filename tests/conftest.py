from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
from typing import Any

import pytest


@dataclass
class _FakeMemcacheClient:
    _store: dict[bytes, bytes] = field(default_factory=dict)

    async def get(self, key: bytes) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: bytes, value: bytes, *args: Any, **kwargs: Any) -> None:
        self._store[key] = value

    async def delete(self, key: bytes) -> None:
        self._store.pop(key, None)

    async def close(self) -> None:
        return None


@dataclass
class _FakeRedisClient:
    _store: dict[str, str] = field(default_factory=dict)

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                deleted += 1
        return deleted

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def keys(self, pattern: str) -> list[str]:
        return [key for key in self._store.keys() if fnmatch.fnmatch(key, pattern)]

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True, scope="session")
def _mock_registry_backends() -> None:
    """Replace memcached/redis clients with in-memory fakes for tests."""
    monkeypatch = pytest.MonkeyPatch()
    try:
        import ofx.runner.registry.memcached as memcached_module
    except Exception:
        memcached_module = None

    if memcached_module and getattr(memcached_module, "aiomcache", None):
        monkeypatch.setattr(
            memcached_module.aiomcache,
            "Client",
            lambda *args, **kwargs: _FakeMemcacheClient(),
        )

    try:
        import ofx.runner.registry.redis as redis_module
    except Exception:
        redis_module = None

    if redis_module and getattr(redis_module, "aioredis", None):
        monkeypatch.setattr(
            redis_module.aioredis,
            "Redis",
            lambda *args, **kwargs: _FakeRedisClient(),
        )

    yield None
    monkeypatch.undo()
