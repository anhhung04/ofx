import shutil
import tempfile
from pathlib import Path

import pytest

from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.utils.workflow_utils import find_workflow

@pytest.mark.asyncio
async def test_script_file_relative_and_absolute(caplog):
    with caplog.at_level("INFO"):
        flow_dir = Path(__file__).parent / "flows"
        flow_path = flow_dir / "test_script_file.yml"

        tmpdir = Path(tempfile.mkdtemp())
        try:
            workflow_dirs = [flow_dir, Path.cwd().absolute()]
            workflow = find_workflow(str(flow_path), tuple(workflow_dirs))

            ctx = RunContext(
                output_path=tmpdir,
                workflow_dirs=workflow_dirs,
            )

            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            assert result.status == RunnerStatus.COMPLETED
            assert "EXAMPLE_SCRIPT_OK" in caplog.text, "Relative script_file should run"
            assert "Random string:" in caplog.text, "Absolute script_file should run"

            log_dir = tmpdir / "logs"
            log_files = list(
                log_dir.glob(
                    "stdout_test-script-file_Run-Python-script-from-default-scripts-directory*.log"
                )
            )
            assert log_files, "Expected log file for script_file step"
            log_content = log_files[0].read_text()
            assert "REQUESTS_OK" in log_content, (
                "script_file should be able to import external deps"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
