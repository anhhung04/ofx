"""Tests for registry key namespacing."""

from pydantic import BaseModel

from ofx.runner.core import BaseRunner, RunContext


class _Model(BaseModel):
    name: str = "m"


class _Runner(BaseRunner[_Model]):
    async def _pre_run(self) -> None: ...
    async def _do_run(self) -> None: ...
    async def _post_run(self) -> None: ...
    def _produce_log(self, message):  # type: ignore[override]
        return str(message)


def test_get_key_includes_class_namespace():
    parent = _Runner(_Model(), RunContext())
    child = _Runner(_Model(), RunContext(), parent=parent)

    key = child.get_key("outputs")
    assert "_Runner:" in key
    assert "_Runner:" in parent.get_key("outputs")
    assert key.count("_Runner:") >= 2
