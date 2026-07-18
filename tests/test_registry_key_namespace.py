"""Tests for registry key namespacing."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ofx.runner import RunContext, Runner

class _Model(BaseModel):
    name: str = "m"

class _Runner(Runner[_Model]):
    async def _pre_run(self) -> None: ...
    async def _do_run(self) -> None: ...
    async def _post_run(self) -> None: ...
    def _produce_log(self, message):
        return str(message)

def test_get_key_includes_class_namespace():
    parent = _Runner(_Model(), RunContext())
    child = _Runner(_Model(), RunContext(), parent=parent)

    key = child.get_key("outputs")
    assert "_Runner:" in key
    assert "_Runner:" in parent.get_key("outputs")
    assert key.count("_Runner:") >= 2

def test_get_key_caches_prefix_for_reuse():
    parent = _Runner(_Model(), RunContext())
    child = _Runner(_Model(), RunContext(), parent=parent)

    first = child.get_key("outputs")
    cached_prefix = child._cached_key_prefix
    second = child.get_key("result")

    assert cached_prefix is not None
    assert first.startswith(cached_prefix)
    assert second.startswith(cached_prefix)

@pytest.mark.asyncio
async def test_registry_call_uses_namespaced_key() -> None:
    calls: list[tuple[str, str, dict[str, int]]] = []

    class _Registry:
        async def set(self, key: str, value: dict[str, int]) -> None:
            calls.append(("set", key, dict(value)))

    runner = object.__new__(Runner)
    runner._registry = _Registry()
    runner._cached_key_prefix = "prefix:"

    await Runner._registry_call(runner, "set", "outputs", {"x": 1})

    assert calls == [("set", "prefix:outputs", {"x": 1})]

@pytest.mark.asyncio
async def test_registry_call_requires_configured_registry() -> None:
    runner = object.__new__(Runner)
    runner._registry = None
    runner._cached_key_prefix = "prefix:"

    with pytest.raises(RuntimeError, match="Runner registry is not configured"):
        await Runner._registry_call(runner, "get", "outputs")
