"""Tests for runner status normalization in external results."""

import pytest
from pydantic import BaseModel

from ofx.runner import RunContext, Runner, RunnerStatus
from ofx.runner.context import normalize_runner_status, normalized_runner_status_value


class _DummyModel(BaseModel):
    name: str = "dummy"


class _NoopRunner(Runner[_DummyModel]):
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


@pytest.mark.asyncio
async def test_get_result_includes_error_and_outputs():
    runner = _NoopRunner()
    runner._error = "boom"
    await runner.reg_set("outputs", {"stdout": "ok"})

    result = await runner.get_result()

    assert result.error == "boom"
    assert result.outputs == {"stdout": "ok"}


def test_status_normalization_helpers_map_finished_only():
    assert normalize_runner_status(RunnerStatus.FINISHED) == RunnerStatus.COMPLETED
    assert normalize_runner_status(RunnerStatus.FAILED) == RunnerStatus.FAILED
    assert normalized_runner_status_value(RunnerStatus.FINISHED) == "completed"
    assert normalized_runner_status_value(RunnerStatus.CANCELED) == "canceled"
