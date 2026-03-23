from pathlib import Path

import pytest

from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.utils.workflow_utils import find_workflow


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_flow(self, caplog):
        with caplog.at_level("DEBUG"):
            import tempfile
            from pathlib import Path

            test_workflow = Path(__file__).parent / "flows" / "test.yml"

            tmpdir = tempfile.mkdtemp()
            try:
                workflow_dirs = [Path(__file__).parent / "flows", Path.cwd().absolute()]
                workflow = find_workflow(str(test_workflow), tuple(workflow_dirs))

                ctx = RunContext(output_path=Path(tmpdir), workflow_dirs=workflow_dirs)
                runner = WorkflowRunner(workflow=workflow, ctx=ctx)
                result = await runner.run()

                assert "command test output" in caplog.text, "Expected output in logs"

                assert result.status == RunnerStatus.COMPLETED
            finally:
                import shutil

                shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_flow_structured_events(self, tmp_path):
        from ofx.runner import run_workflow

        test_workflow = Path(__file__).parent / "flows" / "test.yml"
        event_file = tmp_path / "events.ndjson"
        result = await run_workflow(
            workflow=str(test_workflow),
            output_path=tmp_path,
            event_sink_path=event_file,
        )
        assert result.status == RunnerStatus.COMPLETED
        assert event_file.exists()
        lines = [ln for ln in event_file.read_text().splitlines() if ln.strip()]
        assert lines, "expected structured events"
