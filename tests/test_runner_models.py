"""Tests for runner core models and enums"""

from pathlib import Path

from ofx.models.step import RunType
from ofx.runner.core.models import RunContext, RunnerStatus, RunResult


class TestRunnerStatus:
    """Test RunnerStatus enum"""

    def test_runner_status_values(self):
        """Test all RunnerStatus enum values"""
        assert RunnerStatus.IDLE.value == "idle"
        assert RunnerStatus.RUNNING.value == "running"
        assert RunnerStatus.COMPLETED.value == "completed"
        assert RunnerStatus.FAILED.value == "failed"
        assert RunnerStatus.CANCELED.value == "canceled"

    def test_runner_status_equality(self):
        """Test RunnerStatus equality comparison"""
        assert RunnerStatus.IDLE == RunnerStatus.IDLE
        assert RunnerStatus.COMPLETED != RunnerStatus.FAILED


class TestRunType:
    """Test RunType enum"""

    def test_run_type_values(self):
        """Test all RunType enum values"""
        assert RunType.SCRIPT.value == "script"
        assert RunType.COMMAND.value == "command"
        assert RunType.WORKFLOW.value == "workflow"
        assert RunType.SCRIPT_FILE.value == "script_file"

    def test_run_type_equality(self):
        """Test RunType equality comparison"""
        assert RunType.SCRIPT == RunType.SCRIPT
        assert RunType.COMMAND != RunType.WORKFLOW


class TestRunContext:
    """Test RunContext model"""

    def test_default_run_context(self):
        """Test RunContext with default values"""
        ctx = RunContext()
        assert ctx.inputs == {}
        assert ctx.secrets == {}
        assert isinstance(ctx.envs, dict)
        assert "PATH" in ctx.envs
        assert ctx.output_path is None
        assert ctx.vars == {}
        assert ctx.allow_interactive is False
        assert isinstance(ctx.workflow_dirs, list)

    def test_run_context_with_custom_values(self):
        """Test RunContext with custom values"""
        ctx = RunContext(
            inputs={"key": "value"},
            secrets={"secret_key": "secret_value"},
            envs={"CUSTOM_VAR": "custom_value"},
            output_path=Path("/tmp/test"),
            vars={"custom": "data"},
            allow_interactive=True,
            workflow_dirs=[Path("/custom/dir")],
        )
        assert ctx.inputs == {"key": "value"}
        assert ctx.secrets == {"secret_key": "secret_value"}
        assert ctx.envs["CUSTOM_VAR"] == "custom_value"
        assert ctx.output_path == Path("/tmp/test")
        assert ctx.vars == {"custom": "data"}
        assert ctx.allow_interactive is True
        assert ctx.workflow_dirs == [Path("/custom/dir")]

    def test_run_context_model_copy(self):
        """Test RunContext model_copy preserves data"""
        original = RunContext(
            inputs={"key": "value"},
            vars={"matrix": {"os": "ubuntu"}},
        )
        copy = original.model_copy()
        assert copy.inputs == original.inputs
        assert copy.vars == original.vars
        assert copy is not original

    def test_run_context_model_copy_with_update(self):
        """Test RunContext model_copy with updates"""
        original = RunContext(inputs={"key": "value"})
        updated = original.model_copy(update={"allow_interactive": True})
        assert updated.allow_interactive is True
        assert updated.inputs == {"key": "value"}
        assert original.allow_interactive is False

    def test_run_context_deep_copy(self):
        """Test RunContext deep copy doesn't share mutable objects"""
        original = RunContext(vars={"nested": {"key": "value"}})
        copy = original.model_copy(deep=True)
        copy.vars["nested"]["key"] = "modified"
        assert original.vars["nested"]["key"] == "value"


class TestRunResult:
    """Test RunResult model"""

    def test_run_result_creation(self):
        """Test creating a RunResult"""
        result = RunResult(
            status=RunnerStatus.COMPLETED,
            name="test-run",
            run_id="test-123",
        )
        assert result.status == RunnerStatus.COMPLETED
        assert result.error is None
        assert result.outputs == {}
        assert result.name == "test-run"
        assert result.run_id == "test-123"

    def test_run_result_with_error(self):
        """Test RunResult with error"""
        result = RunResult(
            status=RunnerStatus.FAILED,
            error="Something went wrong",
            name="test-run",
            run_id="test-123",
        )
        assert result.status == RunnerStatus.FAILED
        assert result.error == "Something went wrong"

    def test_run_result_with_outputs(self):
        """Test RunResult with outputs"""
        result = RunResult(
            status=RunnerStatus.COMPLETED,
            outputs={"stdout": "test output", "exit_code": 0},
            name="test-run",
            run_id="test-123",
        )
        assert result.outputs["stdout"] == "test output"
        assert result.outputs["exit_code"] == 0

    def test_run_result_model_dump(self):
        """Test RunResult model_dump"""
        result = RunResult(
            status=RunnerStatus.COMPLETED,
            outputs={"key": "value"},
            name="test-run",
            run_id="test-123",
        )
        dumped = result.model_dump()
        assert dumped["status"] == RunnerStatus.COMPLETED
        assert dumped["outputs"] == {"key": "value"}
        assert dumped["name"] == "test-run"
