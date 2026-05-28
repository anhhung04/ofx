from pathlib import Path
from types import SimpleNamespace

import pytest

from ofx.runner import RunContext, RunnerStatus, WorkflowRunner
from ofx.utils.workflow_utils import find_workflow


class TestFlowRun:
    def test_build_run_context_merges_explicit_env_and_workflow_dir(self, tmp_path):
        from ofx.runner.api import _build_run_context

        workflow_path = tmp_path / "child" / "workflow.yml"
        ctx = _build_run_context(
            inputs={"target": "example.com"},
            output_dir=tmp_path,
            runner_secrets={"API_KEY": "secret"},
            search_paths=[tmp_path / "search"],
            resolved_workflow=SimpleNamespace(workflow_path=workflow_path),
            durable_config=None,
            vars={"project": "demo"},
            event_sink_path=tmp_path / "events.ndjson",
            env={"OFX_TEST_FLAG": "1"},
        )

        assert ctx.inputs == {"target": "example.com"}
        assert ctx.secrets == {"API_KEY": "secret"}
        assert ctx.vars == {"project": "demo"}
        assert ctx.envs["OFX_TEST_FLAG"] == "1"
        assert (tmp_path / "search").absolute() in ctx.workflow_dirs
        assert workflow_path.parent.absolute() in ctx.workflow_dirs

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

    # ── new integration tests ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_parallel_jobs(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-parallel
jobs:
  job1:
    steps:
      - run: echo "job1"
  job2:
    steps:
      - run: echo "job2"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_job_dependencies(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-deps
jobs:
  setup:
    steps:
      - run: echo "setup done"
  main:
    needs: [setup]
    steps:
      - run: echo "main done"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_failure_stops_job(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-failure
jobs:
  failing:
    steps:
      - run: exit 1
      - run: echo "should not reach"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.FAILED

    @pytest.mark.asyncio
    async def test_continue_on_error(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-continue
jobs:
  resilient:
    steps:
      - run: exit 1
        continue-on-error: true
      - run: echo "continued"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_outputs(self, tmp_path, caplog):
        import logging

        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-outputs
jobs:
  outputs_job:
    steps:
      - name: produce
        run: echo "greeting=hello" >> "$OFX_OUTPUTS"
      - name: consume
        run: echo "Got {{ steps.0.outputs.greeting }}"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        with caplog.at_level(logging.DEBUG):
            result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "Got hello" in caplog.text

    @pytest.mark.asyncio
    async def test_matrix_expansion(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-matrix
jobs:
  scan:
    strategy:
      matrix:
        target: [a, b, c]
    steps:
      - run: echo "target={{ matrix.target }}"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_env_vars(self, tmp_path, caplog):
        import logging

        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-env
env:
  MY_VAR: hello_world
jobs:
  check_env:
    steps:
      - run: echo "$MY_VAR"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        with caplog.at_level(logging.DEBUG):
            result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
        assert "hello_world" in caplog.text

    @pytest.mark.asyncio
    async def test_run_if_false_skips(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-runif
jobs:
  conditional:
    steps:
      - run: echo "always runs"
      - run: echo "skipped"
        run_if: "False"
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_inline_python_script(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-script
jobs:
  script_job:
    steps:
      - script: |
          print("hello from python")
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_working_directory(self, tmp_path):
        import yaml

        from ofx.models.workflow import Workflow

        workflow = Workflow.model_validate(
            yaml.safe_load(
                """\
name: test-workdir
jobs:
  wd_job:
    steps:
      - run: pwd
        working-directory: /tmp
"""
            )
        )
        ctx = RunContext(output_path=tmp_path)
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)
        result = await runner.run()
        assert result.status == RunnerStatus.COMPLETED
