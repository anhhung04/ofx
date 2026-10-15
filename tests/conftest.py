from __future__ import annotations

import fnmatch
import os
import sys
import types as types_mod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


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


# ---------------------------------------------------------------------------
# Shared helpers for remote module (git clone) tests
# ---------------------------------------------------------------------------


class _FakeGitRepo:
    """Stand-in for a GitPython ``Repo`` returned by a faked clone."""

    def __init__(self, checkout_calls: list[str] | None = None) -> None:
        self._checkout_calls = checkout_calls
        self.git = types_mod.SimpleNamespace(checkout=self._checkout)

    def _checkout(self, ref: str) -> None:
        if self._checkout_calls is not None:
            self._checkout_calls.append(ref)

    def close(self) -> None:
        pass


def _install_fake_clone(
    monkeypatch: pytest.MonkeyPatch,
    manifest: str,
    *,
    modules: dict[str, str] | None = None,
    fail_clone: bool = False,
    clone_hook=None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Patch ``ofx.modules.remote`` with a no-network git clone layer.

    The clone materialises a cache dir containing ``ofx-modules.yml`` (the
    supplied ``manifest``) plus any ``modules`` files (``name -> source``,
    written under ``modules/``). The GitHub token resolver is stubbed to an
    empty token so tests stay hermetic regardless of machine auth state.

    Returns ``(clone_calls, checkout_calls)`` for assertions.
    """
    clone_calls: list[tuple[str, str]] = []
    checkout_calls: list[str] = []

    monkeypatch.setattr("ofx.settings.get_github_token", lambda: "")

    def fake_clone_from(url: str, target: str, multi_options=None):
        clone_calls.append((url, target))
        if fail_clone:
            raise ImportError(f"boom: {url}")
        target_path = Path(target)
        target_path.mkdir(parents=True, exist_ok=True)
        (target_path / "ofx-modules.yml").write_text(manifest)
        if modules:
            modules_dir = target_path / "modules"
            modules_dir.mkdir(exist_ok=True)
            for name, source in modules.items():
                (modules_dir / name).write_text(source)
        if clone_hook is not None:
            clone_hook(target_path)
        return _FakeGitRepo(checkout_calls)

    monkeypatch.setattr(
        "ofx.modules.remote.git",
        types_mod.SimpleNamespace(
            Repo=types_mod.SimpleNamespace(clone_from=fake_clone_from)
        ),
    )
    return clone_calls, checkout_calls
