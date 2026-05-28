"""Tests for runner status normalization in external results."""

import pytest
from pydantic import BaseModel

from ofx.runner import BaseRunner, RunContext, RunnerStatus


class _DummyModel(BaseModel):
    name: str = "dummy"


class _NoopRunner(BaseRunner[_DummyModel]):
    def __init__(self):
        super().__init__(_DummyModel(), RunContext())

    async def _pre_run(self) -> None:
        pass

    async def _do_run(self) -> None:
        pass

    async def _post_run(self) -> None:
        pass

    def _produce_log(self, message):
        return str(message)


@pytest.mark.asyncio
async def test_get_result_maps_finished_to_completed():
    runner = _NoopRunner()
    runner._state_machine.set_state(RunnerStatus.FINISHED)
    result = await runner.get_result()
    assert result.status == RunnerStatus.COMPLETED
