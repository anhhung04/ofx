"""Tests for runner core models and enums"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ofx.models.step import RunType
from ofx.runner.context import RunContext, RunnerStatus, RunResult
from ofx.runner.metadata import ModelContext
from ofx.runner.runner import Runner


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
        assert RunType.TASK.value == "task"
        assert RunType.PIPE.value == "pipe"

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
        assert ctx.workflow_dir is None
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
            workflow_dir=Path("/tmp/workflow"),
            vars={"custom": "data"},
            allow_interactive=True,
            workflow_dirs=[Path("/custom/dir")],
        )
        assert ctx.inputs == {"key": "value"}
        assert ctx.secrets == {"secret_key": "secret_value"}
        assert ctx.envs["CUSTOM_VAR"] == "custom_value"
        assert ctx.output_path == Path("/tmp/test")
        assert ctx.workflow_dir == Path("/tmp/workflow")
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


class TestRunnerContextUpdates:
    def test_update_context_replaces_ctx_with_merged_copy(self):
        runner = object.__new__(Runner)
        runner.ctx = RunContext(vars={"role": "base"})

        updated = Runner.update_context(runner, mode="scan")

        assert updated.vars["role"] == "base"
        assert updated.mode == "scan"
        assert runner.ctx is updated

    def test_update_env_inputs_secrets_and_vars_delegate_through_updated_context(self):
        runner = object.__new__(Runner)
        runner.ctx = RunContext()

        env_ctx = Runner.update_env(runner, {"A": "1"})
        assert env_ctx.envs["A"] == "1"

        inputs_ctx = Runner.update_inputs(runner, {"target": "example.com"})
        assert inputs_ctx.inputs == {"target": "example.com"}

        secrets_ctx = Runner.update_secrets(runner, {"TOKEN": "secret"})
        assert secrets_ctx.secrets == {"TOKEN": "secret"}

        vars_ctx = Runner.update_vars(runner, {"role": "scan"})
        assert vars_ctx.vars == {"role": "scan"}

    def test_update_env_and_vars_merges_both_maps(self):
        runner = object.__new__(Runner)
        runner.ctx = RunContext(envs={"A": "1"}, vars={"role": "base"})

        updated = Runner.update_env_and_vars(
            runner,
            {"B": "2"},
            {"role": "scan"},
        )

        assert updated.envs["A"] == "1"
        assert updated.envs["B"] == "2"
        assert updated.vars["role"] == "scan"


class TestRunnerRegistryHelpers:
    @pytest.mark.asyncio
    async def test_get_result_defaults_to_empty_outputs_when_registry_has_no_outputs(self):
        class _ResultModel(BaseModel):
            name: str = "dummy"

        class _ResultRunner(Runner[_ResultModel]):
            async def _pre_run(self) -> None: ...
            async def _do_run(self) -> None: ...
            async def _post_run(self) -> None: ...

            async def reg_get(self, _key: str):
                return None

        runner = _ResultRunner(_ResultModel(), RunContext())

        result = await runner.get_result()

        assert result.status == RunnerStatus.IDLE
        assert result.outputs == {}

    @pytest.mark.asyncio
    async def test_get_result_uses_normalized_status_and_outputs(self):
        runner = object.__new__(Runner)
        runner.name = "test-run"
        runner.run_id = "run-1"
        runner._error = None
        runner._state_machine = SimpleNamespace(current_state=RunnerStatus.FINISHED)
        runner._cached_key_prefix = ""

        class _Registry:
            async def get(self, _key):
                return {"stdout": "ok"}

        runner._registry = _Registry()

        result = await Runner.get_result(runner)

        assert result.status == RunnerStatus.COMPLETED
        assert result.outputs == {"stdout": "ok"}

    def test_get_key_and_cached_prefix_helpers_share_computed_prefix(self):
        parent = object.__new__(Runner)
        parent.name = "parent"
        parent.parent = None
        parent._cached_key_prefix = None

        child = object.__new__(Runner)
        child.name = "child"
        child.parent = parent
        child._cached_key_prefix = None

        key = Runner.get_key(child, "outputs")

        assert key.endswith("outputs")
        assert child._cached_key_prefix is not None
        assert Runner._key_prefix(child) == child._cached_key_prefix
        assert child._cached_key_prefix == "Runner:parent:Runner:child:"

    @pytest.mark.asyncio
    async def test_registry_call_uses_namespaced_key_and_method(self):
        calls: list[tuple[str, str, dict[str, int]]] = []

        class _Registry:
            async def set(self, key: str, value: dict[str, int]) -> None:
                calls.append(("set", key, dict(value)))

        runner = object.__new__(Runner)
        runner._registry = _Registry()
        runner._cached_key_prefix = "prefix:"

        await Runner._registry_call(runner, "set", "outputs", {"x": 1})

        assert calls == [("set", "prefix:outputs", {"x": 1})]


class TestRunnerTemplateHelpers:
    def test_build_template_context_merges_ctx_dump_and_vars(self):
        runner = object.__new__(Runner)
        runner.ctx = RunContext(inputs={"target": "example.com"}, vars={"role": "scan"})
        runner.model = SimpleNamespace(name="job-a")
        runner._registry = object()

        context_vars = Runner._build_template_context(runner)

        assert context_vars["inputs"] == {"target": "example.com"}
        assert context_vars["role"] == "scan"

    def test_build_template_context_adds_runner_specific_entries(self):
        runner = object.__new__(Runner)
        runner.ctx = RunContext(inputs={"target": "example.com"}, vars={"role": "scan"})
        runner.model = SimpleNamespace(name="job-a")
        runner._registry = object()

        context_vars = Runner._build_template_context(runner)

        assert context_vars["self"] is runner.model
        assert context_vars["registry"] is runner._registry
        assert context_vars["runner"] is runner
        assert context_vars["ctx"] is runner.ctx
        assert context_vars["vars"] == {"role": "scan"}
        assert callable(context_vars["env"])

    def test_build_template_context_env_lookup_prefers_ctx_env_then_os_default(self, monkeypatch):
        runner = object.__new__(Runner)
        runner.ctx = RunContext(envs={"A": "ctx-value"})
        runner.model = SimpleNamespace(name="job-a")
        runner._registry = object()
        monkeypatch.setenv("B", "os-value")

        env_lookup = Runner._build_template_context(runner)["env"]

        assert env_lookup("A") == "ctx-value"
        assert env_lookup("B") == "os-value"
        assert env_lookup("C", "fallback") == "fallback"

    @pytest.mark.asyncio
    async def test_resolve_job_outputs_logs_and_falls_back_on_error(self):
        class _TemplateModel(BaseModel):
            name: str = "dummy"
            outputs: dict[str, str] = {"target": "{{ bad }}"}

        class _TemplateRunner(Runner[_TemplateModel]):
            async def _pre_run(self) -> None: ...
            async def _do_run(self) -> None: ...
            async def _post_run(self) -> None: ...

        runner = _TemplateRunner(_TemplateModel(), RunContext())
        warnings: list[str] = []
        runner._log_warning = warnings.append

        async def _resolve_template(_value):
            raise RuntimeError("boom")

        runner._resolve_template = _resolve_template

        value = await runner._resolve_job_outputs()

        assert value == {"target": ""}
        assert warnings == ["Failed to resolve output 'target': boom"]

    @pytest.mark.asyncio
    async def test_resolve_template_fields_filters_missing_attributes(self):
        class _TemplateModel(BaseModel):
            name: str = "wf"

        class _TemplateRunner(Runner[_TemplateModel]):
            async def _pre_run(self) -> None: ...
            async def _do_run(self) -> None: ...
            async def _post_run(self) -> None: ...

        runner = _TemplateRunner(_TemplateModel(), RunContext())

        async def _resolve_template(value):
            return f"resolved:{value}"

        runner._resolve_template = _resolve_template

        changed = await runner._resolve_template_fields(["name", "missing"])

        assert changed is True
        assert runner.model.name == "resolved:wf"

    @pytest.mark.asyncio
    async def test_resolve_template_fields_returns_false_when_all_fields_are_missing(self):
        class _TemplateModel(BaseModel):
            name: str = "wf"

        class _TemplateRunner(Runner[_TemplateModel]):
            async def _pre_run(self) -> None: ...
            async def _do_run(self) -> None: ...
            async def _post_run(self) -> None: ...

        runner = _TemplateRunner(_TemplateModel(), RunContext())

        assert await runner._resolve_template_fields(["missing"]) is False
        assert runner.model.name == "wf"

    @pytest.mark.asyncio
    async def test_resolve_job_outputs_uses_shared_resolution(self):
        class _TemplateModel(BaseModel):
            name: str = "wf"
            outputs: dict[str, str] = {"a": "x", "b": "y"}

        class _TemplateRunner(Runner[_TemplateModel]):
            async def _pre_run(self) -> None: ...
            async def _do_run(self) -> None: ...
            async def _post_run(self) -> None: ...

        runner = _TemplateRunner(_TemplateModel(), RunContext())
        runner.model = SimpleNamespace(outputs={"a": "x", "b": "y"})

        async def _resolve_template(value):
            return f"resolved:{value}"

        runner._resolve_template = _resolve_template

        assert await runner._resolve_job_outputs() == {
            "a": "resolved:x",
            "b": "resolved:y",
        }

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
