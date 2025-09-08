import pytest

from ofx.runner.workflow import WorkflowRunner
from ofx.runner.base import RunContext, RunnerStatus


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_flow(self, caplog):
        with caplog.at_level("DEBUG"):
            result = await WorkflowRunner(
                WorkflowRunner.find_flow("./tests/flows/test"), ctx=RunContext()
            ).run()
            assert (
                result.status == RunnerStatus.COMPLETED
            ), f"Flow failed: {result.error}"
            assert "command test output" in caplog.text, "Expected output in logs"
