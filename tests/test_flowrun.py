import pytest

from ofx.runner.workflow import WorkflowRunner
from ofx.runner.base import RunContext, RunnerStatus
from ofx.utils.misc import find_workflow


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_flow(self, caplog):
        with caplog.at_level("DEBUG"):
            from pathlib import Path
            import tempfile
            
            test_workflow = Path(__file__).parent / "flows" / "test.yml"
            
            tmpdir = tempfile.mkdtemp()
            try:
                workflow_dirs = [Path(__file__).parent / "flows", Path.cwd().absolute()]
                workflow = find_workflow(str(test_workflow), tuple(workflow_dirs))
                
                ctx = RunContext(
                    output_path=Path(tmpdir),
                    workflow_dirs=workflow_dirs
                )
                runner = WorkflowRunner(workflow=workflow, ctx=ctx)
                result = await runner.run()
                
                assert "command test output" in caplog.text, "Expected output in logs"
                
                assert 'test' in result.outputs
                assert result.outputs['test']['status'] == RunnerStatus.COMPLETED
            finally:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
