from __future__ import annotations

import asyncio
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest


# -- built-in async test runner (no pytest-asyncio dependency) -----------------
_shared_loop: asyncio.AbstractEventLoop | None = None


def pytest_sessionstart(session):
    """Create one event loop for the entire test session."""
    global _shared_loop
    _shared_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_shared_loop)


def pytest_sessionfinish(session, exitstatus):
    """Clean up the shared event loop."""
    global _shared_loop
    if _shared_loop is None:
        return
    try:
        tasks = asyncio.all_tasks(_shared_loop)
        for task in tasks:
            task.cancel()
        _shared_loop.run_until_complete(
            asyncio.gather(*tasks, return_exceptions=True)
        )
    except Exception:
        pass
    _shared_loop.close()
    asyncio.set_event_loop(None)
    _shared_loop = None


def pytest_pyfunc_call(pyfuncitem):
    """Run ``async def`` test functions through the shared event loop.

    Only fixtures the test function *explicitly* requests are passed in;
    autouse fixtures (``_mock_registry_backends``) are filtered out.
    """
    if not asyncio.iscoroutinefunction(pyfuncitem.obj):
        return None

    import inspect

    sig = inspect.signature(pyfuncitem.obj)
    kwargs = {k: v for k, v in pyfuncitem.funcargs.items() if k in sig.parameters}
    _shared_loop.run_until_complete(pyfuncitem.obj(**kwargs))
    return True


def _is_free_threaded() -> bool:
    """Return True when running under a free‑threaded (no‑GIL) Python build.

    Free‑threaded builds are identified by the ``Py_GIL_DISABLED``
    config flag (``sys._is_gil_enabled()`` returns False on 3.13+) or
    by checking for the ``t`` suffix in the version tag on 3.14+.
    """
    try:
        return not sys._is_gil_enabled()  # type: ignore[attr-defined]
    except AttributeError:
        pass
    vi = sys.version_info
    return getattr(vi, "free_threaded", False) or (
        hasattr(sys, "abiflags") and "t" in sys.abiflags
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests that spawn real subprocesses under free‑threaded Python.

    In free‑threaded builds the ``fork()`` call inside ``subprocess``
    is inherently unsafe — background threads may hold locks that are
    permanently lost in the child.  This is a CPython limitation, not
    specific to any particular runtime (CodeWhale, VS Code, etc.).
    """
    if not _is_free_threaded():
        return

    skip_subprocess = pytest.mark.skip(
        reason="spawns real subprocesses — unsafe under free‑threaded Python (fork locks)"
    )
    skip_files = {"test_sessions.py", "test_project_use.py"}

    for item in items:
        if os.path.basename(item.path) in skip_files:
            item.add_marker(skip_subprocess)


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
        import ofx.runner.registry_backends.memcached as memcached_module
    except Exception:
        memcached_module = None

    if memcached_module and getattr(memcached_module, "aiomcache", None):
        monkeypatch.setattr(
            memcached_module.aiomcache,
            "Client",
            lambda *args, **kwargs: _FakeMemcacheClient(),
        )

    try:
        import ofx.runner.registry_backends.redis as redis_module
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
