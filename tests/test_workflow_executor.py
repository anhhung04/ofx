"""Focused tests for workflow executor helper behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ofx.models.inputs import WorkflowInput
from ofx.models.workflow import Workflow
from ofx.runner import RunContext, RunnerRegistryKeys
from ofx.runner.executors.workflow import (
    WorkflowExecutor,
)


class _ProcessRunner:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.debug: list[str] = []

    def _log_debug(self, message: str) -> None:
        self.debug.append(message)

    def _log_warning(self, message: str) -> None:
        self.warnings.append(message)

    async def _resolve_template(self, value):
        return f"resolved:{value}"


class _MatrixRunner:
    def __init__(self, workflow: Workflow, ctx: RunContext) -> None:
        self.model = workflow
        self.ctx = ctx
        self._is_reused = False
        self.info_messages: list[str] = []

    def _log_info(self, message: str) -> None:
        self.info_messages.append(message)

    def update_vars(self, updates: dict) -> None:
        self.ctx.vars.update(updates)

    def update_context(self, **updates) -> None:
        for key, value in updates.items():
            setattr(self.ctx, key, value)


class _AsyncCallRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, key: str, value: dict) -> None:
        self.calls.append((key, value))


class _RegistryRunner:
    def __init__(self) -> None:
        self.ctx = SimpleNamespace(vars={})
        self._runners = {}
        self._time_guard = None
        self._logged_info: list[str] = []
        self._logged_debug: list[str] = []
        self._registry: dict[str, dict] = {}

    async def reg_set(self, key: str, value: dict) -> None:
        self._registry[key] = value

    async def reg_get(self, key: str):
        return self._registry.get(key)

    def _log_info(self, message: str) -> None:
        self._logged_info.append(message)

    def _log_debug(self, message: str) -> None:
        self._logged_debug.append(message)


class _ProfileRunner:
    def __init__(self, profile_name: str = "") -> None:
        self.model = SimpleNamespace(defaults=SimpleNamespace(profile=profile_name))
        self.ctx = SimpleNamespace(vars={})
        self._profile = None
        self._logged_info: list[str] = []
        self.env_updates: list[dict] = []
        self.var_updates: list[dict] = []

    def _log_info(self, message: str) -> None:
        self._logged_info.append(message)

    def update_env_and_vars(self, env: dict, vars_update: dict) -> None:
        self.env_updates.append(dict(env))
        self.var_updates.append(dict(vars_update))


class _PreRunRunner:
    def __init__(self) -> None:
        defaults = SimpleNamespace(
            run=SimpleNamespace(working_directory=Path("/tmp/work")),
            workflows_base_dir=Path("/tmp/workflows"),
        )
        self.model = SimpleNamespace(
            env={"FOO": "bar"},
            tools=["nmap"],
            defaults=defaults,
            workflow_path=Path("/tmp/workflow/wf.yml"),
            dispatch=None,
            call=None,
            model_dump=lambda exclude=None: {"name": "wf"},
        )
        self.ctx = RunContext()
        self.debug_messages: list[str] = []
        self.env_updates: list[dict] = []
        self.var_updates: list[dict] = []
        self.context_updates: list[dict] = []

    def _log_debug(self, message: str) -> None:
        self.debug_messages.append(message)

    def update_env(self, env: dict) -> None:
        self.env_updates.append(dict(env))

    def update_vars(self, vars_update: dict) -> None:
        self.var_updates.append(dict(vars_update))

    def update_context(self, **updates) -> None:
        self.context_updates.append(dict(updates))


class _PostRunRunner:
    def __init__(self, *, is_reused: bool) -> None:
        self._time_guard = SimpleNamespace(stop=lambda: stops.append("stop"))
        self._is_reused = is_reused
        self._run_dir = Path("/tmp/ofx-run")
        self.debug_messages: list[str] = []

    async def get_result(self):
        return "done"

    def _log_debug(self, message: str) -> None:
        self.debug_messages.append(message)


class _EntrypointRunner:
    def __init__(self, *, is_reused: bool, dispatch=None, call=None) -> None:
        self.model = SimpleNamespace(
            dispatch=dispatch,
            call=call,
            env={},
            tools=["nmap"],
            defaults=SimpleNamespace(
                workflows_base_dir=Path("/tmp/workflows"),
                run=SimpleNamespace(working_directory=Path("/tmp/work")),
            ),
            workflow_path=Path("/tmp/workflow/wf.yml"),
            model_dump=lambda exclude=None: {"name": "wf"},
        )
        self.ctx = RunContext(inputs={"a": 1}, secrets={"s": "x"})
        self._is_reused = is_reused
        self.debug_messages: list[str] = []
        self.input_updates: list[dict] = []
        self.secret_updates: list[dict] = []
        self.env_updates: list[dict] = []
        self.var_updates: list[dict] = []
        self.context_updates: list[dict] = []

    def _log_debug(self, message: str) -> None:
        self.debug_messages.append(message)

    async def _resolve_template_fields(self, _fields) -> None:
        return None

    def update_env(self, env: dict) -> None:
        self.env_updates.append(dict(env))

    def update_vars(self, vars_update: dict) -> None:
        self.var_updates.append(dict(vars_update))

    def update_context(self, **updates) -> None:
        self.context_updates.append(dict(updates))

    def update_inputs(self, values: dict) -> None:
        self.input_updates.append(dict(values))

    def update_secrets(self, values: dict) -> None:
        self.secret_updates.append(dict(values))


@pytest.mark.asyncio
async def test_process_inputs_prefers_primary_key_over_alias() -> None:
    runner = _ProcessRunner()
    blueprint = {
        "target": WorkflowInput(required=True, alias="t", type="string"),
    }

    result = await WorkflowExecutor().process_inputs(
        runner,
        {"target": "primary", "t": "alias"},
        blueprint,
    )

    assert result == {"target": "resolved:primary"}
    assert runner.warnings == [
        "Both input 'target' and its alias 't' are provided. Using value from 'target' and ignoring alias."
    ]


@pytest.mark.asyncio
async def test_process_inputs_raises_for_missing_required_input() -> None:
    runner = _ProcessRunner()
    blueprint = {
        "target": WorkflowInput(required=True, type="string"),
    }

    with pytest.raises(ValueError, match="Input 'target' is required"):
        await WorkflowExecutor().process_inputs(runner, {}, blueprint)

@pytest.mark.asyncio
async def test_process_inputs_raises_for_invalid_value_type() -> None:
    runner = _ProcessRunner()
    blueprint = {
        "count": WorkflowInput(required=True, type="number"),
    }

    with pytest.raises(ValueError, match="Expected type: number"):
        await WorkflowExecutor().process_inputs(runner, {"count": "abc"}, blueprint)


@pytest.mark.asyncio
async def test_process_inputs_raises_for_unsupported_type(monkeypatch) -> None:
    import ofx.runner.executors.workflow as workflow_executor_module

    runner = _ProcessRunner()
    blueprint = {
        "count": WorkflowInput(required=True, type="number"),
    }

    monkeypatch.delitem(
        workflow_executor_module._INPUT_TYPE_MAP,
        "number",
    )

    with pytest.raises(ValueError, match="Unsupported input type 'number'"):
        await WorkflowExecutor().process_inputs(runner, {"count": 1}, blueprint)


@pytest.mark.asyncio
async def test_process_inputs_uses_alias_defaults_and_template_resolution() -> None:
    runner = _ProcessRunner()
    executor = WorkflowExecutor()
    req_inputs = {"t": "alias"}
    blueprint = {
        "target": WorkflowInput(required=True, alias="t", type="string"),
        "count": WorkflowInput(required=False, default=3, type="number"),
    }

    processed = await executor.process_inputs(runner, req_inputs, blueprint)

    assert processed == {
        "t": "resolved:alias",
        "target": "resolved:alias",
        "count": "resolved:3",
    }


@pytest.mark.asyncio
async def test_process_inputs_uses_current_alias_membership_after_alias_pop() -> None:
    runner = _ProcessRunner()
    executor = WorkflowExecutor()
    blueprint = {
        "target": WorkflowInput(required=True, alias="t", type="string"),
        "scope": WorkflowInput(required=True, alias=["t", "s"], type="string"),
    }

    processed = await executor.process_inputs(
        runner,
        {"target": "primary", "t": "shadow", "s": "secondary"},
        blueprint,
    )

    assert processed == {
        "target": "resolved:primary",
        "s": "resolved:secondary",
        "scope": "resolved:secondary",
    }
    assert runner.warnings == [
        "Both input 'target' and its alias 't' are provided. Using value from 'target' and ignoring alias."
    ]


@pytest.mark.asyncio
async def test_process_inputs_warns_when_key_and_alias_are_both_provided() -> None:
    runner = _ProcessRunner()
    blueprint = {
        "target": WorkflowInput(required=True, alias="t", type="string"),
    }

    processed = await WorkflowExecutor().process_inputs(
        runner,
        {"target": "primary", "t": "alias"},
        blueprint,
    )

    assert processed == {"target": "resolved:primary"}
    assert runner.warnings == [
        "Both input 'target' and its alias 't' are provided. Using value from 'target' and ignoring alias."
    ]


@pytest.mark.asyncio
async def test_process_inputs_resolves_defaults_and_templates() -> None:
    runner = _ProcessRunner()
    blueprint = {
        "target": WorkflowInput(required=False, default="{{ inputs.seed }}", type="string"),
        "count": WorkflowInput(required=False, default=3, type="number"),
    }

    result = await WorkflowExecutor().process_inputs(runner, {}, blueprint)

    assert result == {
        "target": "resolved:{{ inputs.seed }}",
        "count": "resolved:3",
    }


def test_expand_list_inputs_to_matrix_updates_only_referenced_jobs() -> None:
    from ofx.models.strategy import MatrixStrategy

    workflow = Workflow.model_validate(
        {
            "name": "Dispatch Matrix",
            "dispatch": {
                "inputs": {
                    "target": {"type": "string"},
                    "count": {"type": "number"},
                }
            },
            "jobs": {
                "scan": {
                    "strategy": {"matrix": {"region": ["us"]}},
                    "steps": [
                        {"run": "echo {{ inputs.target }}"},
                    ]
                },
                "report": {
                    "steps": [
                        {"run": "echo done"},
                    ]
                },
            },
        }
    )
    ctx = RunContext(inputs={"target": ["a", "b"], "count": 2, "keep": "x"})
    runner = _MatrixRunner(workflow, ctx)

    WorkflowExecutor().expand_list_inputs_to_matrix(runner)

    assert workflow.jobs["scan"].strategy is not None
    assert workflow.jobs["scan"].strategy.matrix == {
        "region": ["us"],
        "target": ["a", "b"],
    }
    assert workflow.jobs["report"].strategy is None
    assert runner.ctx.inputs == {"count": 2, "keep": "x"}
    assert runner.ctx.vars["_matrix_input_keys"] == ["target"]
    assert runner.info_messages == ["Auto-expanding input 'target' (2 values) as matrix"]


def test_expand_list_inputs_to_matrix_skips_reused_or_non_matrix_inputs() -> None:
    workflow = Workflow.model_validate(
        {
            "name": "Dispatch Matrix",
            "dispatch": {"inputs": {"target": {"type": "string"}}},
            "jobs": {"scan": {"steps": [{"run": "echo {{ inputs.target }}"}]}},
        }
    )

    reused_runner = _MatrixRunner(workflow, RunContext(inputs={"target": ["a", "b"]}))
    reused_runner._is_reused = True
    WorkflowExecutor().expand_list_inputs_to_matrix(reused_runner)
    assert reused_runner.ctx.inputs == {"target": ["a", "b"]}
    assert reused_runner.ctx.vars == {}
    assert reused_runner.info_messages == []

    scalar_runner = _MatrixRunner(workflow, RunContext(inputs={"target": "a"}))
    WorkflowExecutor().expand_list_inputs_to_matrix(scalar_runner)
    assert scalar_runner.ctx.inputs == {"target": "a"}
    assert scalar_runner.ctx.vars == {}
    assert scalar_runner.info_messages == []

@pytest.mark.asyncio
async def test_post_run_raises_when_reused_child_jobs_failed(monkeypatch) -> None:
    global stops
    stops = []
    runner = _PostRunRunner(is_reused=True)
    runner.model = SimpleNamespace(name="child-workflow", call=None)
    runner._runners = {
        "a": SimpleNamespace(is_failed=True, model=SimpleNamespace(jid="job-a")),
        "b": SimpleNamespace(is_failed=False, model=SimpleNamespace(jid="job-b")),
    }
    monkeypatch.setattr("ofx.runner.executors.workflow.remove_tree", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match=r"Reusable workflow 'child-workflow': 1/2 job\(s\) failed \(job-a\)"):
        await WorkflowExecutor().post_run(runner)


@pytest.mark.asyncio
async def test_post_run_reused_workflow_stores_resolved_outputs(monkeypatch) -> None:
    global stops
    stops = []
    runner = _PostRunRunner(is_reused=True)
    executor = WorkflowExecutor()
    runner.model = SimpleNamespace(
        name="child-workflow",
        call=SimpleNamespace(outputs={"target": "{{ jobs.scan.outputs.host }}"}),
    )
    runner._runners = {}
    runner.registry_updates = _AsyncCallRecorder()

    async def _resolve_template(value):
        return f"resolved:{value}"

    async def _store_summaries(_runner):
        return None

    runner._resolve_template = _resolve_template
    runner.reg_set = runner.registry_updates
    monkeypatch.setattr("ofx.runner.executors.workflow.remove_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(executor, "store_summaries", _store_summaries)

    await executor.post_run(runner)

    assert runner.registry_updates.calls == [
        ("outputs", {"target": "resolved:{{ jobs.scan.outputs.host }}"})
    ]


@pytest.mark.asyncio
async def test_post_run_reused_workflow_skips_empty_resolved_outputs(monkeypatch) -> None:
    global stops
    stops = []
    runner = _PostRunRunner(is_reused=True)
    executor = WorkflowExecutor()
    runner.model = SimpleNamespace(name="child-workflow", call=SimpleNamespace(outputs={}))
    runner._runners = {}
    runner.registry_updates = _AsyncCallRecorder()

    async def _store_summaries(_runner):
        return None

    runner.reg_set = runner.registry_updates
    monkeypatch.setattr("ofx.runner.executors.workflow.remove_tree", lambda *args, **kwargs: None)
    monkeypatch.setattr(executor, "store_summaries", _store_summaries)

    await executor.post_run(runner)

    assert runner.registry_updates.calls == []


@pytest.mark.asyncio
async def test_pre_run_runs_dispatch_for_non_reused_workflow(monkeypatch) -> None:
    runner = _EntrypointRunner(
        is_reused=False,
        dispatch=SimpleNamespace(inputs={"target": "blueprint"}),
    )
    executor = WorkflowExecutor()

    async def _process_inputs(_runner, current_values, blueprint):
        assert current_values == {"a": 1}
        assert blueprint == {"target": "blueprint"}
        return {"target": "resolved"}

    executor.process_inputs = _process_inputs  # type: ignore[method-assign]
    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: "/tmp/test-run-dir",
    )
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", lambda _runner: None)
    monkeypatch.setattr(executor, "apply_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "apply_cli_time_window", lambda _runner: None)
    runner.reg_set = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(run=AsyncMock(return_value=None)),
    )

    await executor.pre_run(runner)

    assert runner.input_updates == [{"target": "resolved"}]


@pytest.mark.asyncio
async def test_pre_run_updates_inputs_and_secrets_for_reuse(monkeypatch) -> None:
    runner = _EntrypointRunner(
        is_reused=True,
        call=SimpleNamespace(inputs={"target": "blueprint"}, secrets={"token": "secret-bp"}),
    )
    executor = WorkflowExecutor()
    seen: list[tuple[dict, dict]] = []
    registered: list[dict[str, str]] = []

    async def _process_inputs(_runner, current_values, blueprint):
        seen.append((dict(current_values), dict(blueprint)))
        return {next(iter(blueprint)): "resolved"}

    executor.process_inputs = _process_inputs  # type: ignore[method-assign]
    monkeypatch.setattr(
        "ofx.utils.log.register_secrets",
        lambda secrets: registered.append(dict(secrets)),
    )
    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: "/tmp/test-run-dir",
    )
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", lambda _runner: None)
    monkeypatch.setattr(executor, "apply_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "apply_cli_time_window", lambda _runner: None)
    runner.reg_set = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(run=AsyncMock(return_value=None)),
    )

    await executor.pre_run(runner)

    assert seen == [
        ({"a": 1}, {"target": "blueprint"}),
        ({"s": "x"}, {"token": "secret-bp"}),
    ]
    assert runner.input_updates == [{"target": "resolved"}]
    assert runner.secret_updates == [{"token": "resolved"}]
    assert registered == [{"s": "x"}]
@pytest.mark.asyncio
async def test_do_run_cleans_up_and_stores_error_payload_on_failed_jobs(monkeypatch) -> None:
    cleanup_calls: list[str] = []
    debug_messages: list[str] = []
    recorder = _AsyncCallRecorder()

    class _ChildRunner:
        def __init__(self, jid: str, *, error: str, fail_cleanup: bool = False) -> None:
            self.model = SimpleNamespace(jid=jid)
            self._error = error
            self._fail_cleanup = fail_cleanup

        async def _post_run(self) -> None:
            cleanup_calls.append(self.model.jid)
            if self._fail_cleanup:
                raise RuntimeError("cleanup boom")

    runner = SimpleNamespace(
        _schedule=[["job-a"]],
        _staged_jobs={"job-a": object()},
        _runners={
            "job-a": _ChildRunner("job-a", error="root-a"),
            "job-b": _ChildRunner("job-b", error="root-b", fail_cleanup=True),
        },
        reg_set=recorder,
        _log_debug=debug_messages.append,
    )

    executor = WorkflowExecutor()
    monkeypatch.setattr("ofx.runner.runner.Runner", _ChildRunner)
    monkeypatch.setattr(
        "ofx.runner.error_helpers.extract_root_error",
        lambda error: f"root:{error}",
    )
    monkeypatch.setattr(executor, "plan_jobs", AsyncMock(return_value=None))

    class _Manager:
        def __init__(self, passed_runner):
            assert passed_runner is runner

        async def run(self, schedule, staged_jobs):
            assert schedule == [["job-a"]]
            assert list(staged_jobs) == ["job-a"]
            return SimpleNamespace(failed_job_ids=["job-a", "job-b"], failed_stage_indices=[0])

    monkeypatch.setattr("ofx.runner.workflow_execution.WorkflowExecutionManager", _Manager)

    async def _store_summaries(_runner):
        return None

    executor.store_summaries = _store_summaries  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match=r"Job failure\(s\):") as exc:
        await executor.do_run(runner)

    assert cleanup_calls == ["job-a", "job-b"]
    assert debug_messages == ["post_run cleanup failed for job-b: cleanup boom"]
    assert str(exc.value) == "Job failure(s):\njob 'job-a': root:root-a\njob 'job-b': root:root-b"
    assert recorder.calls == [
        (
            "errors",
            {
                "message": "Job failure(s):\njob 'job-a': root:root-a\njob 'job-b': root:root-b",
                "failed_jobs": ["job-a", "job-b"],
                "failed_stages": [0],
            },
        )
    ]


@pytest.mark.asyncio
async def test_plan_jobs_sets_runner_fields_and_logs(monkeypatch) -> None:
    runner = SimpleNamespace(
        model=SimpleNamespace(jobs={"job-a": object()}),
        _staged_jobs=None,
        _schedule=None,
        debug_messages=[],
        _log_debug=lambda message: runner.debug_messages.append(message),
    )

    class _Scheduler:
        def __init__(self, jobs):
            assert list(jobs) == ["job-a"]

        def plan(self):
            staged_jobs = {"job-a": object()}
            return SimpleNamespace(staged_jobs=staged_jobs, schedule=[["job-a"]])

    monkeypatch.setattr("ofx.runner.workflow_scheduler.WorkflowScheduler", _Scheduler)

    await WorkflowExecutor().plan_jobs(runner)

    assert list(runner._staged_jobs) == ["job-a"]
    assert runner._schedule == [["job-a"]]
    assert runner.debug_messages == ["Stages: [['job-a']]"]


@pytest.mark.asyncio
async def test_do_run_skips_failure_handler_when_result_clean(monkeypatch) -> None:
    runner = SimpleNamespace(_schedule=[["job-a"]], _staged_jobs={"job-a": object()})
    executor = WorkflowExecutor()

    class _Manager:
        def __init__(self, _runner):
            pass

        async def run(self, _schedule, _staged_jobs):
            return SimpleNamespace(failed_job_ids=[], failed_stage_indices=[])

    monkeypatch.setattr("ofx.runner.workflow_execution.WorkflowExecutionManager", _Manager)
    monkeypatch.setattr(executor, "plan_jobs", AsyncMock(return_value=None))

    await executor.do_run(runner)
@pytest.mark.asyncio
async def test_store_summaries_writes_summary_unified_and_output_projection(monkeypatch) -> None:
    runner = _RegistryRunner()

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a", "jobs": []}

    executor = WorkflowExecutor()
    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )

    await executor.store_summaries(runner)

    assert await runner.reg_get(RunnerRegistryKeys.SUMMARY) == {"workflow_name": "wf-a"}
    assert await runner.reg_get(RunnerRegistryKeys.SUMMARY_UNIFIED) == {
        "workflow_name": "wf-a",
        "jobs": [],
    }
    assert await runner.reg_get(RunnerRegistryKeys.OUTPUTS) == {
        "__summary__": {"workflow_name": "wf-a", "jobs": []}
    }


@pytest.mark.asyncio
async def test_store_summaries_adds_time_window_metadata(monkeypatch) -> None:
    runner = _RegistryRunner()
    runner._time_guard = SimpleNamespace(
        _window=SimpleNamespace(start="09:00", end="17:00"),
        should_abort=True,
    )

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a"}

    executor = WorkflowExecutor()
    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )
    monkeypatch.setattr(
        "ofx.profiles.time_window.check_time_window",
        lambda _window: {"remaining_minutes": 12},
    )

    await executor.store_summaries(runner)

    assert await runner.reg_get(RunnerRegistryKeys.SUMMARY_UNIFIED) == {
        "workflow_name": "wf-a",
        "time_window": {
            "start": "09:00",
            "end": "17:00",
            "remaining_minutes": 12,
            "aborted": True,
        },
    }


@pytest.mark.asyncio
async def test_store_summaries_merges_exported_summaries(monkeypatch) -> None:
    runner = _RegistryRunner()
    runner.ctx.vars["project_path"] = "/tmp/project"

    executor = WorkflowExecutor()

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a"}

    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )

    async def _collect(_runners):
        return [{"_type": "subdomain", "host": "a.example.com"}]

    monkeypatch.setattr(
        "ofx.runner.findings_export.collect_typed_outputs",
        _collect,
    )
    monkeypatch.setattr(
        "ofx.runner.findings_export.export_typed_outputs",
        lambda project_path, all_typed, prefix="": ["subdomains/subdomains.txt"],
    )

    await executor.store_summaries(runner)

    assert runner._logged_info == [
        "Findings exported to project:",
        "subdomains/subdomains.txt",
    ]
    assert await runner.reg_get(RunnerRegistryKeys.OUTPUTS) == {
        "__summary__": {"workflow_name": "wf-a"},
        "__findings_export__": ["subdomains/subdomains.txt"],
    }


@pytest.mark.asyncio
async def test_store_summaries_skips_export_without_project_path(monkeypatch) -> None:
    runner = _RegistryRunner()
    executor = WorkflowExecutor()

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a"}

    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )

    await executor.store_summaries(runner)

    assert await runner.reg_get(RunnerRegistryKeys.OUTPUTS) == {
        "__summary__": {"workflow_name": "wf-a"}
    }


@pytest.mark.asyncio
async def test_store_summaries_skips_export_when_no_typed_outputs(monkeypatch) -> None:
    runner = _RegistryRunner()
    runner.ctx.vars["project_path"] = "/tmp/project"
    executor = WorkflowExecutor()

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a"}

    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )

    async def _collect(_runners):
        return []

    monkeypatch.setattr(
        "ofx.runner.findings_export.collect_typed_outputs",
        _collect,
    )

    await executor.store_summaries(runner)

    assert await runner.reg_get(RunnerRegistryKeys.OUTPUTS) == {
        "__summary__": {"workflow_name": "wf-a"}
    }


@pytest.mark.asyncio
async def test_store_summaries_logs_debug_on_export_failure(monkeypatch) -> None:
    runner = _RegistryRunner()
    runner.ctx.vars["project_path"] = "/tmp/project"

    executor = WorkflowExecutor()

    class _Summary:
        def to_dict(self):
            return {"workflow_name": "wf-a"}

    class _Reporter:
        async def build(self):
            return _Summary()

        async def build_unified(self):
            return {"workflow_name": "wf-a"}

    monkeypatch.setattr(
        "ofx.runner.execution_summary.ExecutionSummaryReporter",
        lambda _runner: _Reporter(),
    )

    async def _collect(_runners):
        return [{"_type": "ip", "ip": "10.0.0.1"}]

    monkeypatch.setattr(
        "ofx.runner.findings_export.collect_typed_outputs",
        _collect,
    )
    monkeypatch.setattr(
        "ofx.runner.findings_export.export_typed_outputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    await executor.store_summaries(runner)

    assert runner._logged_debug == ["Findings export failed: boom"]




@pytest.mark.asyncio
async def test_apply_profile_skips_without_profile_name() -> None:
    runner = _ProfileRunner("")

    await WorkflowExecutor().apply_profile(runner)

    assert runner._profile is None
    assert runner._logged_info == []
    assert runner.env_updates == []


@pytest.mark.asyncio
async def test_apply_profile_prefers_cli_profile_override(monkeypatch) -> None:
    from ofx.profiles.models import OFXProfile

    runner = _ProfileRunner("")
    runner.ctx.vars["_cli_profile_name"] = "stealth"
    profile = OFXProfile(threads=4)

    monkeypatch.setattr(
        "ofx.profiles.manager.get_profile_manager",
        lambda: SimpleNamespace(resolve_or_default=lambda name: profile if name == "stealth" else None),
    )

    await WorkflowExecutor().apply_profile(runner)

    assert runner._profile is profile
    assert runner._logged_info == ["Applying profile: stealth"]
    assert runner.var_updates[0]["profile_model"] is profile


@pytest.mark.asyncio
async def test_apply_profile_skips_when_profile_resolution_returns_none(monkeypatch) -> None:
    runner = _ProfileRunner("stealth")
    monkeypatch.setattr(
        "ofx.profiles.manager.get_profile_manager",
        lambda: SimpleNamespace(resolve_or_default=lambda _name: None),
    )

    await WorkflowExecutor().apply_profile(runner)

    assert runner._profile is None
    assert runner._logged_info == []
    assert runner.env_updates == []


@pytest.mark.asyncio
async def test_apply_profile_updates_runtime_and_activates_time_window(monkeypatch) -> None:
    from ofx.profiles.models import OFXProfile, TimeWindow

    runner = _ProfileRunner("stealth")
    profile = OFXProfile(
        threads=5,
        env={"FOO": "bar"},
        time_window=TimeWindow(
            enabled=True,
            start="09:00",
            end="17:00",
            days=["mon", "tue"],
            timezone="UTC",
        ),
    )
    executor = WorkflowExecutor()
    monkeypatch.setattr(
        "ofx.profiles.manager.get_profile_manager",
        lambda: SimpleNamespace(resolve_or_default=lambda _name: profile),
    )

    activation: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _activate(_runner, *args, **kwargs):
        activation.append((args, kwargs))

    monkeypatch.setattr(executor, "_activate_time_window", _activate)

    await executor.apply_profile(runner)

    assert runner._profile is profile
    assert runner._logged_info == ["Applying profile: stealth"]
    env = runner.env_updates[0]
    assert env["FOO"] == "bar"
    assert env["OFX_THREADS"] == "5"
    assert env["OFX_PROFILE_THREADS"] == "5"
    assert env["OFX_PROFILE_ENV"] == '{"FOO": "bar"}'
    assert env["OFX_PROFILE_TIME_WINDOW"] == '{"abort_on_expire": true, "days": ["mon", "tue"], "enabled": true, "end": "17:00", "start": "09:00", "timezone": "UTC", "warn_before_minutes": 10}'
    assert env["OFX_PROFILE_JSON"]
    assert runner.var_updates[0]["profile_model"] is profile
    assert runner.var_updates[0]["profile"]["threads"] == 5
    assert len(activation) == 1
    args, kwargs = activation[0]
    assert args[0] == profile.time_window
    assert kwargs["denied_message"] == (
        "Profile 'stealth' restricts execution to 09:00–17:00 on Mon, Tue (UTC)."
    )
    assert kwargs.get("active_message") is None


@pytest.mark.asyncio
async def test_apply_profile_only_includes_non_default_profile_envs(monkeypatch) -> None:
    runner = _ProfileRunner("stealth")
    profile = SimpleNamespace(
        env={},
        rate_limit=30,
        threads=10,
        timeout_minutes=90,
        delay=2.0,
        jitter=0.5,
        proxy="socks5://127.0.0.1:9050",
        user_agent="CustomAgent/1.0",
        time_window=SimpleNamespace(enabled=False),
        model_dump=lambda: {"name": "stealth"},
    )

    monkeypatch.setattr(
        "ofx.profiles.manager.get_profile_manager",
        lambda: SimpleNamespace(resolve_or_default=lambda _name: profile),
    )

    await WorkflowExecutor().apply_profile(runner)

    env = runner.env_updates[0]
    assert env["OFX_RATE_LIMIT"] == "30"
    assert env["OFX_TIMEOUT"] == "90"
    assert env["OFX_DELAY"] == "2.0"
    assert env["OFX_JITTER"] == "0.5"
    assert env["OFX_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["OFX_USER_AGENT"] == "CustomAgent/1.0"
    assert env["OFX_PROFILE_NAME"] == "stealth"
    assert env["OFX_PROFILE_RATE_LIMIT"] == "30"
    assert env["OFX_PROFILE_TIMEOUT_MINUTES"] == "90"
    assert env["OFX_PROFILE_USER_AGENT"] == "CustomAgent/1.0"
    assert '"name": "stealth"' in env["OFX_PROFILE_JSON"]
    assert '"rate_limit": 30' in env["OFX_PROFILE_JSON"]
    assert '"threads": 10' in env["OFX_PROFILE_JSON"]
    assert env["http_proxy"] == "socks5://127.0.0.1:9050"
    assert env["https_proxy"] == "socks5://127.0.0.1:9050"
    assert env["HTTP_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["HTTPS_PROXY"] == "socks5://127.0.0.1:9050"
    assert env["ALL_PROXY"] == "socks5://127.0.0.1:9050"


@pytest.mark.asyncio
async def test_apply_profile_skips_default_profile_envs(monkeypatch) -> None:
    runner = _ProfileRunner("stealth")
    profile = SimpleNamespace(
        env={},
        rate_limit=None,
        threads=10,
        timeout_minutes=60,
        delay=None,
        jitter=None,
        proxy=None,
        user_agent=None,
        time_window=SimpleNamespace(enabled=False),
        model_dump=lambda: {"name": "stealth"},
    )

    monkeypatch.setattr(
        "ofx.profiles.manager.get_profile_manager",
        lambda: SimpleNamespace(resolve_or_default=lambda _name: profile),
    )

    await WorkflowExecutor().apply_profile(runner)

    env = runner.env_updates[0]
    assert env["OFX_PROFILE_NAME"] == "stealth"
    assert env["OFX_PROFILE_THREADS"] == "10"
    assert env["OFX_PROFILE_TIMEOUT_MINUTES"] == "60"
    assert env["OFX_PROFILE_TIME_WINDOW"] == "namespace(enabled=False)"
    assert '"name": "stealth"' in env["OFX_PROFILE_JSON"]


def test_apply_cli_time_window_returns_without_runner_var() -> None:
    runner = SimpleNamespace(
        _time_guard=None,
        _is_reused=False,
        ctx=SimpleNamespace(vars={}),
    )
    calls: list[object] = []
    executor = WorkflowExecutor()
    executor._activate_time_window = lambda _runner, *args, **kwargs: calls.append((args, kwargs))  # type: ignore[method-assign]

    executor.apply_cli_time_window(runner)

    assert calls == []


def test_apply_cli_time_window_resolves_window_and_messages() -> None:
    runner = SimpleNamespace(
        _time_guard=None,
        _is_reused=False,
        ctx=SimpleNamespace(vars={"_cli_time_window": "09:00-17:00"}),
    )
    activations: list[tuple[tuple[object, ...], dict[str, object]]] = []
    executor = WorkflowExecutor()
    executor._activate_time_window = lambda _runner, *args, **kwargs: activations.append((args, kwargs))  # type: ignore[method-assign]

    executor.apply_cli_time_window(runner)

    args, kwargs = activations[0]
    window = args[0]
    assert window.start == "09:00"
    assert window.end == "17:00"
    assert kwargs["denied_message"] == (
        "CLI --time-window restricts execution to 09:00–17:00."
    )
    assert kwargs["active_message"] == "Time window active: 09:00–17:00"

def test_activate_time_window_checks_starts_and_logs(monkeypatch) -> None:
    warnings: list[str] = []
    infos: list[str] = []
    starts: list[str] = []
    errors: list[str] = []
    runner = SimpleNamespace(
        _log_warning=warnings.append,
        _log_info=lambda message: infos.append(message),
        _log_error=errors.append,
    )

    guard_callbacks: list[object] = []

    class _Guard:
        def __init__(self, **kwargs):
            guard_callbacks.append(kwargs["on_abort"])

        def start(self):
            starts.append("start")

    monkeypatch.setattr(
        "ofx.profiles.time_window.check_time_window",
        lambda _window: {"allowed": True, "message": "warn"},
    )
    monkeypatch.setattr("ofx.profiles.time_window.TimeWindowGuard", _Guard)

    WorkflowExecutor._activate_time_window(
        runner,
        object(),
        denied_message="denied",
        active_message="Time window active",
    )

    assert warnings == ["warn"]
    assert starts == ["start"]
    assert infos == ["Time window active"]
    guard_callbacks[0]("expired")
    assert errors == ["🛑 expired - workflow will be aborted"]


@pytest.mark.asyncio
async def test_pre_run_runs_setup_steps_in_order(monkeypatch) -> None:
    runner = _PreRunRunner()
    executor = WorkflowExecutor()
    calls: list[str] = []

    class _OutputPath:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            assert parents is True
            assert exist_ok is True
            calls.append("output_path")

    runner.ctx.output_path = _OutputPath()

    async def _resolve_template_fields(_fields):
        calls.append("resolve")

    def _expand(_runner):
        calls.append("expand_matrix")

    def _log(message: str):
        if message.startswith("Resolved workflow: "):
            calls.append("resolved_log")
            return
        if message.startswith("Workflow Dispatch: "):
            calls.append("entrypoint")
            return
        if message.startswith("Workflow Call: "):
            return
        assert message.startswith("Processed context: ")
        calls.append("log")

    def _update_context(**updates):
        if "workflow_dir" in updates:
            calls.append("init_context")
            return
        assert "workflow_dirs" in updates
        calls.append("workflow_dirs")

    def _update_env(_env):
        calls.append("init_context")

    def _update_vars(_vars):
        calls.append("init_context")

    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: "/tmp/test-run-dir",
    )
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", _expand)
    runner._resolve_template_fields = _resolve_template_fields
    runner.update_env = _update_env
    runner.update_vars = _update_vars
    runner.update_context = _update_context
    runner._log_debug = _log

    monkeypatch.setattr(executor, "apply_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "apply_cli_time_window", lambda _runner: calls.append("cli_window"))
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(
            run=AsyncMock(side_effect=lambda: calls.append("install_tools"))
        ),
    )

    async def _reg_set(_key, _value):
        calls.append("store_model")

    runner.reg_set = _reg_set

    await executor.pre_run(runner)

    assert calls == [
        "resolve",
        "resolved_log",
        "output_path",
        "init_context",
        "init_context",
        "init_context",
        "entrypoint",
        "expand_matrix",
        "workflow_dirs",
        "log",
        "init_context",
        "cli_window",
        "store_model",
        "install_tools",
    ]


@pytest.mark.asyncio
async def test_pre_run_initializes_run_context(monkeypatch, tmp_path) -> None:
    runner = _PreRunRunner()
    executor = WorkflowExecutor()
    runner.ctx.output_path = None

    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: str(tmp_path / "run-dir"),
    )

    async def _resolve_template_fields(_fields):
        return None

    runner._resolve_template_fields = _resolve_template_fields
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", lambda _runner: None)
    monkeypatch.setattr(executor, "apply_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "apply_cli_time_window", lambda _runner: None)
    runner.reg_set = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(run=AsyncMock(return_value=None)),
    )

    await executor.pre_run(runner)

    assert runner._run_dir == tmp_path / "run-dir"
    assert runner.env_updates == [
        {"OFX_RUN_DIR": str(tmp_path / "run-dir")},
        {"FOO": "bar"},
    ]
    assert runner.var_updates == [{"working_directory": Path("/tmp/work")}]
    assert runner.context_updates[0] == {"workflow_dir": Path("/tmp/workflow")}
@pytest.mark.asyncio
async def test_post_run_finalizes_reused_workflow_then_summaries_and_cleanup(monkeypatch) -> None:
    global stops
    stops = []
    runner = _PostRunRunner(is_reused=True)
    runner.model = SimpleNamespace(name="child-workflow", call=SimpleNamespace(outputs={}))
    runner._runners = {}
    executor = WorkflowExecutor()
    calls: list[str] = []

    async def _store_summaries(_runner):
        calls.append("summaries")

    def _remove_tree(path, *, on_error, label):
        calls.append("cleanup")
        assert path == runner._run_dir
        assert label == "run dir"

    monkeypatch.setattr(executor, "store_summaries", _store_summaries)
    monkeypatch.setattr("ofx.runner.executors.workflow.remove_tree", _remove_tree)

    await executor.post_run(runner)

    assert stops == ["stop"]
    assert calls == ["summaries", "cleanup"]
    assert runner.debug_messages == ["result: done"]


@pytest.mark.asyncio
async def test_post_run_skips_reused_finalization_for_normal_workflow(monkeypatch) -> None:
    global stops
    stops = []
    runner = _PostRunRunner(is_reused=False)
    executor = WorkflowExecutor()
    calls: list[str] = []

    async def _store_summaries(_runner):
        calls.append("summaries")

    def _remove_tree(path, *, on_error, label):
        calls.append("cleanup")
        assert path == runner._run_dir
        assert label == "run dir"

    monkeypatch.setattr(executor, "store_summaries", _store_summaries)
    monkeypatch.setattr("ofx.runner.executors.workflow.remove_tree", _remove_tree)

    await executor.post_run(runner)

    assert stops == ["stop"]
    assert calls == ["summaries", "cleanup"]


def test_on_failure_cleans_up_run_dir(monkeypatch) -> None:
    executor = WorkflowExecutor()
    runner = SimpleNamespace(_run_dir=Path("/tmp/ofx-run"))
    calls: list[Path] = []

    monkeypatch.setattr(
        "ofx.runner.executors.workflow.remove_tree",
        lambda path, *, on_error, label: calls.append(path),
    )

    import asyncio
    asyncio.run(executor.on_failure(runner))

    assert calls == [runner._run_dir]


@pytest.mark.asyncio
async def test_pre_run_runs_runtime_steps_in_order_after_context_prep(monkeypatch) -> None:
    runner = _PreRunRunner()
    executor = WorkflowExecutor()
    calls: list[str] = []

    def _update_env(_env):
        calls.append("env")

    async def _apply_profile(_runner):
        calls.append("profile")

    def _apply_cli_window(_runner):
        calls.append("cli_window")

    async def _reg_set(_key, _value):
        calls.append("store_model")

    async def _install_tools(_runner):
        calls.append("install_tools")

    runner.update_env = _update_env
    runner._resolve_template_fields = AsyncMock(return_value=None)
    runner.update_vars = lambda _vars: None
    runner.update_context = lambda **_updates: None
    runner._log_debug = lambda _message: None
    runner.reg_set = _reg_set
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", lambda _runner: None)
    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: "/tmp/test-run-dir",
    )
    monkeypatch.setattr(executor, "apply_profile", _apply_profile)
    monkeypatch.setattr(executor, "apply_cli_time_window", _apply_cli_window)
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(run=lambda: _install_tools(runner)),
    )

    await executor.pre_run(runner)

    assert calls == ["env", "env", "profile", "cli_window", "store_model", "install_tools"]
