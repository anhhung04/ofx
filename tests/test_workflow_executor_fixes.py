"""Regression tests for workflow-execution slice fixes (Slice D).

Covers findings H2, M4, M5, M6, M8, L1 (execution_summary + cloud parts),
L4, L10, L13, L16, and the workflow.py part of L6 from docs/runner-review.md.

Each test fails against the pre-fix code and passes after the fix.
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.pipe import PipeConfig
from ofx.models.workflow import ToolConfig, Workflow
from ofx.runner import RunContext, RunnerRegistryKeys
from ofx.runner.executors.fleet import FleetExecutor
from ofx.runner.executors.parallel import (
    parallel_run_settings,
    run_limited_fail_fast,
)
from ofx.runner.executors.workflow import WorkflowExecutor
from ofx.runner.pipe import PipeExecution, PipeRunner
from ofx.runner.runner import Runner
from ofx.runner.tool_installer import ToolInstallerRunner
from ofx.runner.workflow_execution import WorkflowExecutionManager

# ---------------------------------------------------------------------------
# H2 — unnamed jobs get backfilled names → unique registry namespaces
# ---------------------------------------------------------------------------

def _two_unnamed_jobs_workflow() -> Workflow:
    return Workflow.model_validate(
        {
            "name": "wf",
            "jobs": {
                "scan": {
                    "steps": [{"module": "shell", "with": {"cmd": "echo scan"}}]
                },
                "report": {
                    "steps": [{"module": "shell", "with": {"cmd": "echo report"}}]
                },
            },
        }
    )


def test_unnamed_jobs_backfill_name_from_jid() -> None:
    workflow = _two_unnamed_jobs_workflow()

    # Before the fix both names stayed "" → the registry namespace prefix
    # (derived from the job name) collided between the two jobs.
    assert workflow.jobs["scan"].name == "scan"
    assert workflow.jobs["report"].name == "report"
    assert workflow.jobs["scan"].jid == "scan"
    assert workflow.jobs["report"].jid == "report"


def test_unnamed_jobs_have_distinct_namespace_prefixes() -> None:
    workflow = _two_unnamed_jobs_workflow()

    namespaces = {f"JobRunner:{job.name}" for job in workflow.jobs.values()}
    assert len(namespaces) == 2
    # No empty-name prefix remains (the pre-fix collision case).
    assert "JobRunner:" not in namespaces


@pytest.mark.asyncio
async def test_unnamed_jobs_do_not_cross_contaminate_registry_outputs() -> None:
    from ofx.runner.context import context_copy
    from ofx.runner.job import JobRunner
    from ofx.runner.workflow import WorkflowRunner

    workflow = _two_unnamed_jobs_workflow()
    parent = WorkflowRunner(workflow, RunContext())
    scan_runner = JobRunner(
        workflow.jobs["scan"], context_copy(parent.ctx), parent=parent
    )
    report_runner = JobRunner(
        workflow.jobs["report"], context_copy(parent.ctx), parent=parent
    )

    assert scan_runner.get_key("outputs") != report_runner.get_key("outputs")

    await scan_runner.reg_set(RunnerRegistryKeys.OUTPUTS, {"host": "scan-1"})
    assert await report_runner.reg_get(RunnerRegistryKeys.OUTPUTS) is None
    assert await scan_runner.reg_get(RunnerRegistryKeys.OUTPUTS) == {"host": "scan-1"}


# ---------------------------------------------------------------------------
# M4 — workflow failure only runs _post_run for jobs that have not completed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_run_failure_skips_post_run_for_completed_jobs(monkeypatch) -> None:
    cleanup_calls: list[str] = []
    registry_calls: list[tuple[str, dict]] = []

    class _ChildRunner:
        def __init__(self, jid: str, *, is_success: bool, error: str | None) -> None:
            self.model = SimpleNamespace(jid=jid)
            self._error = error
            self.is_success = is_success

        async def _post_run(self) -> None:
            cleanup_calls.append(self.model.jid)

    runner = SimpleNamespace(
        _schedule=[["job-a"]],
        _staged_jobs={"job-a": object()},
        _runners={
            # job-a completed its own lifecycle (post_run already ran).
            "job-a": _ChildRunner("job-a", is_success=True, error=None),
            # job-b failed → its runner never reached post_run.
            "job-b": _ChildRunner("job-b", is_success=False, error="root-b"),
        },
        reg_set=AsyncMock(side_effect=lambda key, value: registry_calls.append((key, value))),
        _log_debug=lambda message: None,
    )

    executor = WorkflowExecutor()
    monkeypatch.setattr("ofx.runner.runner.Runner", _ChildRunner)
    monkeypatch.setattr(
        "ofx.runner.error_helpers.extract_root_error",
        lambda error: f"root:{error}",
    )
    monkeypatch.setattr(executor, "plan_jobs", AsyncMock(return_value=None))

    class _Manager:
        def __init__(self, _runner):
            pass

        async def run(self, _schedule, _staged_jobs):
            return SimpleNamespace(
                failed_job_ids=["job-a", "job-b"],
                failed_stage_indices=[0],
            )

    monkeypatch.setattr(
        "ofx.runner.workflow_execution.WorkflowExecutionManager", _Manager
    )

    async def _store_summaries(_runner) -> None:
        return None

    executor.store_summaries = _store_summaries

    with pytest.raises(RuntimeError, match=r"Job failure\(s\):"):
        await executor.do_run(runner)

    # Completed job-a must NOT re-run post_run (cloud jobs would repeat
    # download_outputs/destroy_instance); failed job-b still needs cleanup.
    assert cleanup_calls == ["job-b"]
    assert registry_calls[0][0] == RunnerRegistryKeys.ERRORS


# ---------------------------------------------------------------------------
# M5 — time-window guard is stopped on the failure path too
# ---------------------------------------------------------------------------

def test_on_failure_stops_time_window_guard(monkeypatch) -> None:
    stops: list[str] = []
    runner = SimpleNamespace(
        _time_guard=SimpleNamespace(stop=lambda: stops.append("stop")),
        _run_dir=None,
    )
    executor = WorkflowExecutor()
    monkeypatch.setattr(
        "ofx.runner.executors.workflow.remove_tree", lambda *args, **kwargs: None
    )

    asyncio.run(executor.on_failure(runner))

    # Pre-fix the guard was only stopped in post_run → leaked poller.
    assert stops == ["stop"]


# ---------------------------------------------------------------------------
# M6 — FleetExecutor.post_run must not reference runner._logger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fleet_post_run_logs_cleanup_errors_via_runner_log_debug(tmp_path) -> None:
    parent_dir = tmp_path / "chunk-dir"
    parent_dir.mkdir()
    chunk = parent_dir / "chunk.txt"
    chunk.write_text("data")
    # Keep an extra file so the parent-dir rmdir fails → on_error fires.
    (parent_dir / "keep.txt").write_text("keep")

    messages: list[str] = []
    runner = SimpleNamespace(
        _chunk_files=[chunk],
        _log_debug=messages.append,
    )

    await FleetExecutor().post_run(runner)

    # Pre-fix this raised AttributeError (runner._logger does not exist);
    # the cleanup error must be routed through runner._log_debug instead.
    assert any("chunk dir" in message for message in messages)
    assert all(isinstance(message, str) for message in messages)


# ---------------------------------------------------------------------------
# M8 — memory gate: no literal %%, debug once, wait outside the semaphore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wait_for_memory_logs_single_percent_not_literal_double(monkeypatch, caplog) -> None:
    manager = object.__new__(WorkflowExecutionManager)
    manager._mem_limit = 90

    def _no_proc(*_args, **_kwargs):
        raise OSError("no /proc/meminfo")

    monkeypatch.setattr("builtins.open", _no_proc)

    with caplog.at_level(logging.DEBUG, logger="ofx"):
        await manager._wait_for_memory()

    unavailable = [
        record.getMessage()
        for record in caplog.records
        if "Memory usage check unavailable" in record.getMessage()
    ]
    assert len(unavailable) == 1
    assert "0%" in unavailable[0]
    assert "0%%" not in unavailable[0]


@pytest.mark.asyncio
async def test_wait_for_memory_logs_unavailable_once_after_high_usage_poll(
    monkeypatch, caplog
) -> None:
    manager = object.__new__(WorkflowExecutionManager)
    manager._mem_limit = 90
    reads = {"count": 0}

    def _meminfo_reader(*_args, **_kwargs):
        reads["count"] += 1
        if reads["count"] == 1:
            # High usage → the wait loop polls again.
            return io.StringIO("MemTotal: 100 kB\nMemAvailable: 1 kB\n")
        raise OSError("gone")

    monkeypatch.setattr("builtins.open", _meminfo_reader)
    monkeypatch.setattr(
        "ofx.runner.workflow_execution.asyncio.sleep", AsyncMock(return_value=None)
    )

    with caplog.at_level(logging.DEBUG, logger="ofx"):
        await manager._wait_for_memory()

    unavailable = [
        record.getMessage()
        for record in caplog.records
        if "Memory usage check unavailable" in record.getMessage()
    ]
    # The unavailable notice is logged once per wait, not on every poll.
    assert len(unavailable) == 1
    assert "0%" in unavailable[0]


@pytest.mark.asyncio
async def test_memory_wait_happens_outside_job_semaphore_slot() -> None:
    events: list[str] = []
    manager = object.__new__(WorkflowExecutionManager)
    manager._parent = SimpleNamespace(_log_info=lambda message: None)
    manager._max_parallel_jobs = 1
    manager._job_semaphore = asyncio.Semaphore(1)
    manager._mem_limit = 90

    async def _wait_for_memory() -> None:
        events.append(f"wait-{sum(1 for e in events if e.startswith('wait-'))}")
        await asyncio.sleep(0.05)

    manager._wait_for_memory = _wait_for_memory

    class _FakeRunner:
        def __init__(self, jid: str) -> None:
            self._jid = jid
            self.is_failed = False

        async def run(self) -> None:
            events.append(f"run-{self._jid}")
            await asyncio.sleep(0.01)

    failed = await manager._run_stage(
        0,
        {"a": _FakeRunner("a"), "b": _FakeRunner("b")},
    )

    assert failed == []
    assert [e for e in events if e.startswith("run-")] == ["run-a", "run-b"]
    # Both memory waits are entered before the first job runs, proving the
    # gate no longer holds a job-semaphore slot while waiting.
    assert events.index("wait-1") < events.index("run-a")


# ---------------------------------------------------------------------------
# L1 — registry key literals → RunnerRegistryKeys members (stored strings
#      stay identical)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_summary_uses_registry_key_member() -> None:
    from ofx.runner.context import RunnerStatus
    from ofx.runner.execution_summary import ExecutionSummaryReporter

    seen: list[object] = []

    class _FakeRunner:
        def __init__(self) -> None:
            self.model = SimpleNamespace(name="job-a", jid="job-a", steps=[object()])
            self.status = RunnerStatus.COMPLETED
            self._error = None

        async def reg_get(self, key):
            seen.append(key)
            return {"jid": "job-a"}

        def duration_ms(self) -> int:
            return 5

    reporter = ExecutionSummaryReporter(
        SimpleNamespace(runners={"job-a": _FakeRunner()})
    )
    await reporter._job_summaries()

    # Pre-fix the reporter looked up the raw "execution" literal; the key
    # must be the shared member (stored string stays "execution").
    assert seen == [RunnerRegistryKeys.EXECUTION]
    assert seen[0] is RunnerRegistryKeys.EXECUTION
    assert seen[0] == "execution"


@pytest.mark.asyncio
async def test_cloud_executor_stores_instance_metadata_under_key_member(
    monkeypatch,
) -> None:
    from ofx.models.cloud import CloudConfig
    from ofx.runner.executors.cloud import CloudExecutor

    cfg = CloudConfig(provider="static", host="10.0.0.1")
    registry_updates: list[tuple[str, dict]] = []
    runner = SimpleNamespace(
        _cloud_config=cfg,
        model=SimpleNamespace(name="job-name", jid="job-1"),
        _instance=None,
        _log_info=lambda _message: None,
    )
    executor = CloudExecutor()

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    async def _provision_instance(_runner, _cfg):
        _runner._instance = SimpleNamespace(
            instance_id="i-123",
            ip="10.0.0.1",
            provider="static",
            region="local",
        )

    async def _reg_set(key, value):
        registry_updates.append((key, value))

    runner.reg_set = _reg_set
    monkeypatch.setattr(executor, "_prepare_job_context", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "provision_instance", _provision_instance)
    monkeypatch.setattr(executor, "_store_job_model", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ofx.runner.executors.cloud.register_secrets", lambda _values: None
    )

    await executor.pre_run(runner)

    # Stored string must stay "cloud_instance" while using the enum member.
    assert registry_updates == [
        (RunnerRegistryKeys.CLOUD_INSTANCE, {
            "instance_id": "i-123",
            "ip": "10.0.0.1",
            "provider": "static",
            "region": "local",
        })
    ]
    assert registry_updates[0][0] is RunnerRegistryKeys.CLOUD_INSTANCE
    assert registry_updates[0][0] == "cloud_instance"


# ---------------------------------------------------------------------------
# L4 — PipeRunner / ToolInstallerRunner reuse the parent registry
# ---------------------------------------------------------------------------

def test_pipe_runner_reuses_parent_registry() -> None:
    parent = SimpleNamespace(registry="parent-registry")
    pipe = PipeRunner(
        PipeExecution(pipe=PipeConfig(input="[]")),
        RunContext(),
        parent=parent,
    )
    assert pipe.registry == "parent-registry"


def test_pipe_runner_standalone_gets_private_registry() -> None:
    pipe = PipeRunner(
        PipeExecution(pipe=PipeConfig(input="[]")),
        RunContext(),
    )
    assert pipe.registry is not None


def test_tool_installer_runner_reuses_parent_registry() -> None:
    parent = SimpleNamespace(registry="parent-registry")
    installer = ToolInstallerRunner(
        {"test_tool": ToolConfig(install="echo hi")},
        RunContext(),
        parent=parent,
    )
    assert installer.registry == "parent-registry"


def test_tool_installer_runner_standalone_gets_private_registry() -> None:
    installer = ToolInstallerRunner({}, RunContext())
    assert installer.registry is not None


# ---------------------------------------------------------------------------
# L10 — max_parallel=None means unbounded (no Semaphore(None) crash)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_limited_fail_fast_treats_none_max_parallel_as_unbounded() -> None:
    calls: list[int] = []

    async def run_item(index: int, _value: int) -> int:
        calls.append(index)
        return index

    results = await run_limited_fail_fast(
        [10, 20, 30],
        max_parallel=None,
        fail_fast=True,
        run_item=run_item,
        is_failure=lambda _result: False,
    )

    assert results == [0, 1, 2]
    assert calls == [0, 1, 2]


def test_parallel_run_settings_none_max_parallel_falls_back_to_item_count() -> None:
    strategy = SimpleNamespace(max_parallel=None, fail_fast=False)
    assert parallel_run_settings(strategy, item_count=7) == (7, False)


# ---------------------------------------------------------------------------
# L13 — Runner has no decorative base __slots__; dynamic executor attrs work
# ---------------------------------------------------------------------------

def test_runner_supports_dynamic_executor_attributes() -> None:
    runner = Runner(SimpleNamespace(name="m"), RunContext())

    # Executors attach these ad-hoc (workflow time guard, fleet chunks, …);
    # the pre-fix base __slots__ (with no subclass __dict__ guarantee) made
    # this a misleading AttributeError for bare Runner instances.
    runner._time_guard = "guard"
    runner._chunk_files = []

    assert runner._time_guard == "guard"
    assert runner._chunk_files == []
    assert "_time_guard" in runner.__dict__


# ---------------------------------------------------------------------------
# L16 — context update helper + no in-place Job.strategy mutation
# ---------------------------------------------------------------------------

class _PreRunProbe:
    """Minimal runner double recording update_context() calls."""

    def __init__(self) -> None:
        defaults = SimpleNamespace(
            run=SimpleNamespace(working_directory=Path("/tmp/work")),
            workflows_base_dir=Path("/tmp/workflows"),
        )
        self.model = SimpleNamespace(
            env={},
            tools=[],
            defaults=defaults,
            workflow_path=Path("/tmp/workflow/wf.yml"),
            dispatch=None,
            call=None,
            model_dump=lambda exclude=None: {"name": "wf"},
        )
        self.ctx = RunContext()
        self.context_updates: list[dict] = []

    def _log_debug(self, message: str) -> None:
        return None

    def update_env(self, env: dict) -> None:
        return None

    def update_vars(self, vars_update: dict) -> None:
        return None

    def update_context(self, **updates) -> None:
        self.context_updates.append(dict(updates))


@pytest.mark.asyncio
async def test_pre_run_sets_output_path_via_context_update_helper(
    monkeypatch, tmp_path
) -> None:
    runner = _PreRunProbe()
    runner.ctx.output_path = None
    executor = WorkflowExecutor()

    monkeypatch.setattr(
        "ofx.runner.executors.workflow.tempfile.mkdtemp",
        lambda prefix: str(tmp_path / "run-dir"),
    )
    runner._resolve_template_fields = AsyncMock(return_value=None)
    monkeypatch.setattr(executor, "expand_list_inputs_to_matrix", lambda _runner: None)
    monkeypatch.setattr(executor, "apply_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "apply_cli_time_window", lambda _runner: None)
    runner.reg_set = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "ofx.runner.tool_installer.ToolInstallerRunner",
        lambda **kwargs: SimpleNamespace(run=AsyncMock(return_value=None)),
    )

    await executor.pre_run(runner)

    # Pre-fix this was a direct ctx.output_path assignment; now it goes
    # through the context update helper like every other context mutation.
    assert {"output_path": tmp_path / "run-dir"} in runner.context_updates


class _MatrixProbe:
    def __init__(self, workflow: Workflow, ctx: RunContext) -> None:
        self.model = workflow
        self.ctx = ctx
        self._is_reused = False

    def _log_info(self, message: str) -> None:
        return None

    def update_vars(self, updates: dict) -> None:
        self.ctx.vars.update(updates)

    def update_context(self, **updates) -> None:
        for key, value in updates.items():
            setattr(self.ctx, key, value)


def test_expand_list_inputs_to_matrix_does_not_mutate_shared_strategy() -> None:
    workflow = Workflow.model_validate(
        {
            "name": "Dispatch Matrix",
            "dispatch": {"inputs": {"target": {"type": "string"}}},
            "jobs": {
                "scan": {
                    "strategy": {"matrix": {"region": ["us"]}},
                    "steps": [
                        {
                            "module": "shell",
                            "with": {"cmd": "echo {{ inputs.target }}"},
                        }
                    ],
                },
            },
        }
    )
    original_strategy = workflow.jobs["scan"].strategy
    runner = _MatrixProbe(workflow, RunContext(inputs={"target": ["a", "b"]}))

    WorkflowExecutor().expand_list_inputs_to_matrix(runner)

    # The shared strategy object must not be mutated in place.
    assert original_strategy.matrix == {"region": ["us"]}
    # The job now references a copy carrying the merged matrix.
    assert workflow.jobs["scan"].strategy.matrix == {
        "region": ["us"],
        "target": ["a", "b"],
    }
    assert workflow.jobs["scan"].strategy is not original_strategy


# ---------------------------------------------------------------------------
# L6 (workflow part) — no get_result() deepcopy for the debug log
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_run_debug_log_does_not_deepcopy_full_result(monkeypatch) -> None:
    stops: list[str] = []
    runner = SimpleNamespace(
        _time_guard=SimpleNamespace(stop=lambda: stops.append("stop")),
        _is_reused=False,
        _run_dir=None,
        status=SimpleNamespace(value="COMPLETED"),
        debug_messages=[],
    )
    get_result_calls: list[str] = []

    async def _get_result():
        get_result_calls.append("get_result")
        return "done"

    runner.get_result = _get_result
    runner._log_debug = runner.debug_messages.append

    executor = WorkflowExecutor()

    async def _store_summaries(_runner) -> None:
        return None

    executor.store_summaries = _store_summaries
    monkeypatch.setattr(
        "ofx.runner.executors.workflow.remove_tree", lambda *args, **kwargs: None
    )

    await executor.post_run(runner)

    # Pre-fix the debug log called get_result() (deep-copying every output);
    # now the status-only log never touches the registry outputs.
    assert get_result_calls == []
    assert runner.debug_messages == ["result: status=COMPLETED"]
