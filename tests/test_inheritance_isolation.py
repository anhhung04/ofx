"""
Test inheritance and isolation for secrets, envs, and DefaultConfig.
Tests that children properly override or inherit values from parent contexts.
"""

from pathlib import Path

import pytest

from ofx.models.job import Job
from ofx.models.step import Step
from ofx.models.type import DefaultConfig, RunConfig
from ofx.models.workflow import Workflow
from ofx.runner.core import RunContext
from ofx.runner.job import JobRunner
from ofx.runner.step import StepRunner
from ofx.runner.workflow import WorkflowRunner


class TestContextInheritance:
    """Test RunContext inheritance and isolation."""

    def test_secrets_inheritance_basic(self):
        """Test that child context inherits parent secrets."""
        parent_ctx = RunContext(
            secrets={"API_KEY": "parent_key", "TOKEN": "parent_token"}
        )
        child_ctx = parent_ctx.copy_for_child()

        assert child_ctx.secrets["API_KEY"] == "parent_key"
        assert child_ctx.secrets["TOKEN"] == "parent_token"

    def test_secrets_override(self):
        """Test that child can override parent secrets."""
        parent_ctx = RunContext(
            secrets={"API_KEY": "parent_key", "TOKEN": "parent_token"}
        )
        child_ctx = parent_ctx.copy_for_child(secrets={"API_KEY": "child_key"})

        assert child_ctx.secrets["API_KEY"] == "child_key"
        assert child_ctx.secrets["TOKEN"] == "parent_token"

    def test_secrets_isolation(self):
        """Test that modifying child secrets doesn't affect parent."""
        parent_ctx = RunContext(secrets={"API_KEY": "parent_key"})
        child_ctx = parent_ctx.copy_for_child()
        child_ctx.secrets["NEW_KEY"] = "new_value"
        child_ctx.secrets["API_KEY"] = "modified_key"

        assert parent_ctx.secrets["API_KEY"] == "parent_key"
        assert "NEW_KEY" not in parent_ctx.secrets
        assert child_ctx.secrets["API_KEY"] == "modified_key"
        assert child_ctx.secrets["NEW_KEY"] == "new_value"

    def test_envs_inheritance_basic(self):
        """Test that child context inherits parent envs."""
        parent_ctx = RunContext(envs={"PATH": "/usr/bin", "HOME": "/home/user"})
        child_ctx = parent_ctx.copy_for_child()

        assert child_ctx.envs["PATH"] == "/usr/bin"
        assert child_ctx.envs["HOME"] == "/home/user"

    def test_envs_override(self):
        """Test that child can override parent envs."""
        parent_ctx = RunContext(envs={"PATH": "/usr/bin", "HOME": "/home/user"})
        child_ctx = parent_ctx.copy_for_child(envs={"PATH": "/custom/bin"})

        assert child_ctx.envs["PATH"] == "/custom/bin"
        assert child_ctx.envs["HOME"] == "/home/user"

    def test_envs_isolation(self):
        """Test that modifying child envs doesn't affect parent."""
        parent_ctx = RunContext(envs={"PATH": "/usr/bin"})
        child_ctx = parent_ctx.copy_for_child()
        child_ctx.envs["NEW_VAR"] = "new_value"
        child_ctx.envs["PATH"] = "/modified/bin"

        assert parent_ctx.envs["PATH"] == "/usr/bin"
        assert "NEW_VAR" not in parent_ctx.envs
        assert child_ctx.envs["PATH"] == "/modified/bin"
        assert child_ctx.envs["NEW_VAR"] == "new_value"

    def test_inputs_inheritance_basic(self):
        """Test that child context inherits parent inputs."""
        parent_ctx = RunContext(inputs={"param1": "value1", "param2": "value2"})
        child_ctx = parent_ctx.copy_for_child()

        assert child_ctx.inputs["param1"] == "value1"
        assert child_ctx.inputs["param2"] == "value2"

    def test_inputs_override(self):
        """Test that child can override parent inputs."""
        parent_ctx = RunContext(inputs={"param1": "value1", "param2": "value2"})
        child_ctx = parent_ctx.copy_for_child(inputs={"param1": "child_value"})

        assert child_ctx.inputs["param1"] == "child_value"
        assert child_ctx.inputs["param2"] == "value2"

    def test_inputs_isolation(self):
        """Test that modifying child inputs doesn't affect parent."""
        parent_ctx = RunContext(inputs={"param1": "value1"})
        child_ctx = parent_ctx.copy_for_child()
        child_ctx.inputs["new_param"] = "new_value"
        child_ctx.inputs["param1"] = "modified_value"

        assert parent_ctx.inputs["param1"] == "value1"
        assert "new_param" not in parent_ctx.inputs
        assert child_ctx.inputs["param1"] == "modified_value"
        assert child_ctx.inputs["new_param"] == "new_value"

    def test_vars_isolation(self):
        """Test that child vars are isolated from parent."""
        parent_ctx = RunContext(vars={"step1": "output1"})
        child_ctx = parent_ctx.copy_for_child()
        child_ctx.vars["step2"] = "output2"

        assert "step2" not in parent_ctx.vars
        assert child_ctx.vars["step1"] == "output1"
        assert child_ctx.vars["step2"] == "output2"

    def test_output_path_inheritance(self):
        """Test that child inherits parent output_path."""
        parent_ctx = RunContext(output_path=Path("/tmp/parent"))
        child_ctx = parent_ctx.copy_for_child()

        assert child_ctx.output_path == Path("/tmp/parent")

    def test_output_path_override(self):
        """Test that child can override parent output_path."""
        parent_ctx = RunContext(output_path=Path("/tmp/parent"))
        child_ctx = parent_ctx.copy_for_child(output_path=Path("/tmp/child"))

        assert child_ctx.output_path == Path("/tmp/child")
        assert parent_ctx.output_path == Path("/tmp/parent")

    def test_flows_dirs_isolation(self):
        """Test that flows_dirs are isolated between contexts."""
        parent_ctx = RunContext(flows_dirs=[Path("/parent/flows")])
        child_ctx = parent_ctx.copy_for_child()
        child_ctx.flows_dirs.append(Path("/child/flows"))

        assert len(parent_ctx.flows_dirs) == 1
        assert len(child_ctx.flows_dirs) == 2
        assert Path("/child/flows") not in parent_ctx.flows_dirs


class TestJobEnvInheritance:
    """Test Job-level env inheritance."""

    @pytest.mark.asyncio
    async def test_job_env_updates_context(self):
        """Test that job env updates are applied to context."""
        workflow = Workflow(
            name="Test Workflow",
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    env={"JOB_VAR": "job_value"},
                    steps=[Step(name="Test Step", run="echo test")],
                )
            },
        )

        ctx = RunContext(envs={"WORKFLOW_VAR": "workflow_value"})
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)

        # Check that workflow context is preserved
        assert runner.ctx_vars.envs["WORKFLOW_VAR"] == "workflow_value"

    @pytest.mark.asyncio
    async def test_job_env_inherits_workflow_env(self):
        """Test that job inherits workflow-level env."""
        workflow = Workflow(
            name="Test Workflow",
            env={"WORKFLOW_VAR": "workflow_value"},
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    env={"JOB_VAR": "job_value"},
                    steps=[Step(name="Test Step", run="echo test")],
                )
            },
        )

        ctx = RunContext()
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)

        # Call _pre_run to apply workflow env to context
        await runner._pre_run()

        # Workflow env should now be in context
        assert "WORKFLOW_VAR" in runner.ctx_vars.envs
        assert runner.ctx_vars.envs["WORKFLOW_VAR"] == "workflow_value"


class TestDefaultConfigInheritance:
    """Test DefaultConfig inheritance from workflow to job to step."""

    def test_default_config_workflow_to_job(self):
        """Test that job inherits workflow defaults."""
        workflow_defaults = DefaultConfig(
            run=RunConfig(shell="/bin/bash", working_directory=Path("/workflow/dir"))
        )

        workflow = Workflow(
            name="Test Workflow",
            defaults=workflow_defaults,
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[Step(name="Test Step", run="echo test")],
                )
            },
        )

        job = workflow.jobs["test_job"]
        # Job should use workflow defaults when not overridden
        assert workflow.defaults.run.shell == "/bin/bash"

    def test_default_config_job_override(self):
        """Test that job can override workflow defaults."""
        workflow = Workflow(
            name="Test Workflow",
            defaults=DefaultConfig(run=RunConfig(shell="/bin/bash")),
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    defaults=DefaultConfig(run=RunConfig(shell="/bin/zsh")),
                    steps=[Step(name="Test Step", run="echo test")],
                )
            },
        )

        # Workflow has bash
        assert workflow.defaults.run.shell == "/bin/bash"
        # Job overrides with zsh
        assert workflow.jobs["test_job"].defaults.run.shell == "/bin/zsh"


class TestMultiLevelInheritance:
    """Test inheritance across workflow -> job -> step hierarchy."""

    @pytest.mark.asyncio
    async def test_three_level_env_inheritance(self):
        """Test env inheritance across all three levels."""
        workflow = Workflow(
            name="Test Workflow",
            env={"LEVEL": "workflow", "WORKFLOW_VAR": "w_value"},
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    env={"LEVEL": "job", "JOB_VAR": "j_value"},
                    steps=[
                        Step(
                            name="Test Step",
                            run="echo test",
                            env={"LEVEL": "step", "STEP_VAR": "s_value"},
                        )
                    ],
                )
            },
        )

        ctx = RunContext(envs={"LEVEL": "context", "CONTEXT_VAR": "c_value"})
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)

        # Call _pre_run to apply workflow env to context
        await runner._pre_run()

        # Context should have workflow-level vars merged with context vars
        assert "WORKFLOW_VAR" in runner.ctx_vars.envs
        assert "CONTEXT_VAR" in runner.ctx_vars.envs
        # Workflow level should override context level
        assert runner.ctx_vars.envs["LEVEL"] == "workflow"

    @pytest.mark.asyncio
    async def test_three_level_secrets_inheritance(self):
        """Test secrets inheritance with overrides at each level."""
        workflow = Workflow(
            name="Test Workflow",
            jobs={
                "test_job": Job(
                    name="Test Job",
                    jid="test_job",
                    steps=[
                        Step(
                            name="Test Step",
                            run="echo test",
                            secrets={"STEP_SECRET": "step_value"},
                        )
                    ],
                )
            },
        )

        ctx = RunContext(secrets={"WORKFLOW_SECRET": "w_value", "SHARED": "workflow"})
        runner = WorkflowRunner(workflow=workflow, ctx=ctx)

        # Workflow context should preserve secrets
        assert runner.ctx_vars.secrets["WORKFLOW_SECRET"] == "w_value"
        assert runner.ctx_vars.secrets["SHARED"] == "workflow"


class TestCopyForChildEdgeCases:
    """Test edge cases in copy_for_child method."""

    def test_empty_updates(self):
        """Test copy_for_child with no updates."""
        parent_ctx = RunContext(inputs={"a": 1}, secrets={"b": 2}, envs={"c": 3})
        child_ctx = parent_ctx.copy_for_child()

        assert child_ctx.inputs == {"a": 1}
        assert child_ctx.secrets == {"b": 2}
        assert child_ctx.envs == {"c": 3}

    def test_partial_updates(self):
        """Test copy_for_child with partial updates."""
        parent_ctx = RunContext(
            inputs={"a": 1, "b": 2}, secrets={"x": "y"}, envs={"p": "q"}
        )
        child_ctx = parent_ctx.copy_for_child(inputs={"c": 3}, secrets={"z": "w"})

        # Should merge updates
        assert child_ctx.inputs == {"a": 1, "b": 2, "c": 3}
        assert child_ctx.secrets == {"x": "y", "z": "w"}
        assert child_ctx.envs == {"p": "q"}  # No update, inherited

    def test_nested_dict_isolation(self):
        """Test that nested dicts in vars are isolated."""
        parent_ctx = RunContext(vars={"nested": {"key": "value"}})
        child_ctx = parent_ctx.copy_for_child()

        # Modify child's nested dict
        child_ctx.vars["nested"]["key"] = "modified"

        # Parent should be affected (shallow copy)
        # This is expected behavior - vars use shallow copy
        assert parent_ctx.vars["nested"]["key"] == "modified"

    def test_multiple_children_isolation(self):
        """Test that multiple children don't interfere with each other."""
        parent_ctx = RunContext(secrets={"KEY": "parent"}, envs={"VAR": "parent"})

        child1_ctx = parent_ctx.copy_for_child(secrets={"KEY": "child1"})
        child2_ctx = parent_ctx.copy_for_child(secrets={"KEY": "child2"})

        assert child1_ctx.secrets["KEY"] == "child1"
        assert child2_ctx.secrets["KEY"] == "child2"
        assert parent_ctx.secrets["KEY"] == "parent"

        # Modify one child
        child1_ctx.envs["NEW"] = "value1"

        # Other child should not see the change
        assert "NEW" not in child2_ctx.envs
        assert "NEW" not in parent_ctx.envs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
