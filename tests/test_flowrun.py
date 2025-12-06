import pytest

from ofx.runner.workflow import WorkflowRunner
from ofx.runner.base import RunContext, RunnerStatus


class TestFlowRun:
    @pytest.mark.asyncio
    async def test_flow(self, caplog):
        with caplog.at_level("DEBUG"):
            # Use the actual test workflow file path
            from pathlib import Path
            import tempfile
            
            test_workflow = Path(__file__).parent / "flows" / "test.yml"
            
            # Create temporary output directory that persists during execution
            tmpdir = tempfile.mkdtemp()
            try:
                ctx = RunContext(output_path=Path(tmpdir))
                # Create temporary runner to find workflow
                temp_runner = WorkflowRunner(workflow=None, ctx=ctx)
                temp_runner._model = None
                temp_runner._ctx = ctx
                workflow = temp_runner.find_flow(str(test_workflow))
                
                # Now create actual runner with found workflow
                runner = WorkflowRunner(workflow=workflow, ctx=ctx)
                result = await runner.run()
                
                # Check that the workflow ran (jobs completed even if post-run fails)
                assert "command test output" in caplog.text, "Expected output in logs"
                
                # Verify jobs completed successfully
                assert 'test' in result.outputs
                assert result.outputs['test']['status'] == RunnerStatus.COMPLETED
            finally:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
