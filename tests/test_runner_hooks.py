"""Tests for BaseRunner lifecycle hooks ordering."""

import pytest
from pydantic import BaseModel

from ofx.runner.core import BaseRunner, RunContext, RunnerStatus


class _DummyModel(BaseModel):
    name: str = "dummy"


class _HookedRunner(BaseRunner[_DummyModel]):
    def __init__(self, should_fail: bool = False):
        super().__init__(_DummyModel(), RunContext())
        self.should_fail = should_fail
        self.events: list[str] = []

    async def _pre_run(self) -> None:
        self.events.append("pre_run")

    async def _do_run(self) -> None:
        self.events.append("do_run")
        if self.should_fail:
            raise RuntimeError("boom")

    async def _post_run(self) -> None:
        self.events.append("post_run")

    def _produce_log(self, message):
        return str(message)

    async def _on_start(self) -> None:
        self.events.append("on_start")

    async def _on_success(self) -> None:
        self.events.append("on_success")

    async def _on_error(self, error: Exception) -> None:
        self.events.append("on_error")

    async def _on_finish(self) -> None:
        self.events.append("on_finish")


@pytest.mark.asyncio
async def test_hook_order_success():
    runner = _HookedRunner(should_fail=False)
    result = await runner.run()

    assert result.status == RunnerStatus.COMPLETED
    assert runner.events == [
        "on_start",
        "pre_run",
        "do_run",
        "post_run",
        "on_success",
        "on_finish",
    ]


@pytest.mark.asyncio
async def test_hook_order_failure():
    runner = _HookedRunner(should_fail=True)
    result = await runner.run()

    assert result.status == RunnerStatus.FAILED
    assert runner.events == [
        "on_start",
        "pre_run",
        "do_run",
        "on_error",
        "on_finish",
    ]
