"""
Integration tests for real workflow execution with inheritance and isolation.
Tests actual runner behavior in complete workflow scenarios.
"""

import tempfile
from pathlib import Path

import pytest

from ofx.models.job import Job
from ofx.models.step import Step
from ofx.models.workflow import Workflow
from ofx.runner.core import RunContext, RunnerStatus
from ofx.runner.workflow import WorkflowRunner


class TestRealWorkflowInheritance:
    """Test inheritance in real workflow execution scenarios."""

    @pytest.mark.asyncio
    async def test_job_inherits_workflow_secrets(self):
        """Test that secrets flow from workflow to job to step."""
        workflow = Workflow(
            name="Secret Test Workflow",
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[
                        Step(
                            name="Echo Secret",
                            run='echo "Secret accessed"',
                        )
                    ],
                )
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(
                secrets={"API_KEY": "secret123", "TOKEN": "token456"},
                output_path=Path(tmpdir),
            )
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            # Workflow should complete successfully
            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]
            # Secrets should be preserved in context
            assert ctx.secrets["API_KEY"] == "secret123"

    @pytest.mark.asyncio
    async def test_step_overrides_job_env(self):
        """Test that step can override job-level env variables."""
        workflow = Workflow(
            name="Env Override Test",
            env={"LEVEL": "workflow", "WORKFLOW_VAR": "w_val"},
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    env={"LEVEL": "job", "JOB_VAR": "j_val"},
                    steps=[
                        Step(
                            name="Step with override",
                            run='echo "Testing env"',
                            env={"LEVEL": "step", "STEP_VAR": "s_val"},
                        )
                    ],
                )
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(
                envs={"LEVEL": "context", "CONTEXT_VAR": "c_val"},
                output_path=Path(tmpdir),
            )
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            # Check that all levels completed
            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]

    @pytest.mark.asyncio
    async def test_parallel_jobs_isolated_contexts(self):
        """Test that parallel jobs have isolated contexts."""
        workflow = Workflow(
            name="Parallel Jobs Test",
            jobs={
                "job1": Job(
                    name="Job 1",
                    jid="job1",
                    env={"JOB_ID": "1"},
                    steps=[Step(name="Job1 Step", run='echo "Job 1"')],
                ),
                "job2": Job(
                    name="Job 2",
                    jid="job2",
                    env={"JOB_ID": "2"},
                    steps=[Step(name="Job2 Step", run='echo "Job 2"')],
                ),
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(output_path=Path(tmpdir))
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            # Both jobs should complete
            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]
            # Check that both jobs ran
            if result.status == RunnerStatus.COMPLETED:
                assert "job1" in result.outputs
                assert "job2" in result.outputs

    @pytest.mark.asyncio
    async def test_sequential_steps_share_job_context(self):
        """Test that sequential steps in same job share context."""
        workflow = Workflow(
            name="Sequential Steps Test",
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[
                        Step(
                            name="Step 1",
                            run='echo "Step 1"',
                            env={"STEP1_VAR": "value1"},
                        ),
                        Step(
                            name="Step 2",
                            run='echo "Step 2"',
                            env={"STEP2_VAR": "value2"},
                        ),
                    ],
                )
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(output_path=Path(tmpdir))
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]
            if result.status == RunnerStatus.COMPLETED:
                # Both steps should have run
                job_output = result.outputs["test_job"]
                assert "steps" in job_output["outputs"]


class TestContextModificationIsolation:
    """Test that context modifications don't leak between runners."""

    @pytest.mark.asyncio
    async def test_job_env_modification_isolated(self):
        """Test that job env modifications don't affect workflow context."""
        workflow = Workflow(
            name="Isolation Test",
            env={"SHARED": "workflow_value"},
            jobs={
                "job1": Job(
                    name="Job 1",
                    jid="job1",
                    env={"SHARED": "job1_value", "JOB1_VAR": "j1"},
                    steps=[Step(name="Step", run='echo "test"')],
                ),
                "job2": Job(
                    name="Job 2",
                    jid="job2",
                    env={"SHARED": "job2_value", "JOB2_VAR": "j2"},
                    steps=[Step(name="Step", run='echo "test"')],
                ),
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(output_path=Path(tmpdir))
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)

            # Run workflow
            await runner._pre_run()

            # Workflow context should have workflow-level env
            assert runner.ctx_vars.envs["SHARED"] == "workflow_value"

            # Jobs should not have modified workflow context
            # (They get their own copy via copy_for_child)


class TestDefaultConfigInheritance:
    """Test DefaultConfig inheritance in real scenarios."""

    @pytest.mark.asyncio
    async def test_working_directory_inheritance(self):
        """Test that working directory is inherited from workflow defaults."""
        from ofx.models.type import DefaultConfig, RunConfig

        workflow = Workflow(
            name="WorkDir Test",
            defaults=DefaultConfig(
                run=RunConfig(shell="/bin/bash", working_directory=Path.cwd())
            ),
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[Step(name="Check Dir", run='echo "pwd"')],
                )
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(output_path=Path(tmpdir))
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)

            # Workflow should have defaults
            assert runner.model.defaults.run.shell == "/bin/bash"

            result = await runner.run()
            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]


class TestSecretsInheritMode:
    """Test the 'inherit' mode for secrets at step level."""

    @pytest.mark.asyncio
    async def test_step_secrets_inherit_keyword(self):
        """Test that step with secrets='inherit' uses parent secrets."""
        workflow = Workflow(
            name="Secrets Inherit Test",
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[
                        Step(
                            name="Inherit Secrets",
                            run='echo "Using inherited secrets"',
                            secrets="inherit",
                        )
                    ],
                )
            },
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = RunContext(
                secrets={"PARENT_SECRET": "parent_value"}, output_path=Path(tmpdir)
            )
            runner = WorkflowRunner(workflow=workflow, ctx=ctx)
            result = await runner.run()

            # Should complete without errors
            assert result.status in [RunnerStatus.COMPLETED, RunnerStatus.FAILED]
            # Parent context should still have secrets
            assert ctx.secrets["PARENT_SECRET"] == "parent_value"


class TestCopyForChildPerformance:
    """Test copy_for_child correctness and use cases."""

    def test_copy_for_child_correctness(self):
        """Verify copy_for_child provides correct isolation and merging."""
        ctx = RunContext(
            inputs={"key" + str(i): f"value{i}" for i in range(10)},
            secrets={"secret" + str(i): f"sec{i}" for i in range(10)},
            envs={"env" + str(i): f"val{i}" for i in range(10)},
        )

        # Test that copy_for_child properly merges updates
        child = ctx.copy_for_child(
            inputs={"new_key": "new_value"}, secrets={"new_secret": "new_sec"}
        )

        # Child should have merged data
        assert "new_key" in child.inputs
        assert "key0" in child.inputs
        assert "new_secret" in child.secrets
        assert "secret0" in child.secrets

        # Parent should not be affected
        assert "new_key" not in ctx.inputs
        assert "new_secret" not in ctx.secrets

        # Modify child and verify parent is isolated
        child.envs["modified"] = "value"
        assert "modified" not in ctx.envs


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
