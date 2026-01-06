import shutil
import tempfile
from pathlib import Path

import pytest

from ofx.runner.workflow import WorkflowRunner
from ofx.runner.base import RunContext, RunnerStatus
from ofx.utils.misc import find_workflow


@pytest.mark.asyncio
async def test_script_file_relative_and_absolute(caplog):
    with caplog.at_level("INFO"):
        flow_dir = Path(__file__).parent / "flows"
        flow_path = flow_dir / "test_script_file.yml"

        tmpdir = Path(tempfile.mkdtemp())
        try:
            workflow_dirs = [flow_dir, Path.cwd().absolute()]
            flow_path, workflow = find_workflow(str(flow_path), tuple(workflow_dirs))

            ctx = RunContext(
                output_path=tmpdir,
                workflow_dirs=workflow_dirs,
                workflow_dir=flow_path.parent,
            )

            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            assert result.status == RunnerStatus.COMPLETED
            assert "EXAMPLE_SCRIPT_OK" in caplog.text, "Relative script_file should run"
            assert "Random string:" in caplog.text, "Absolute script_file should run"
            assert "REQUESTS_OK" in caplog.text, "script_file should be able to import external deps"
            assert "Inline script in" in caplog.text, "Should be able to import ofx modules in scripts"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
