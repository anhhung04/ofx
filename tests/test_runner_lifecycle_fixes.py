"""Regression tests for runner lifecycle fixes (H1, M1, M2, H3, L1, L12, L14, L3).

Coverage per finding:

- **H1** — registry cleanup only runs for the root runner; a child runner
  sharing the parent's registry must not close it.
- **M1** — the durable-resume path still runs finalization (``runner_finish``
  event, root registry cleanup, final checkpoints, auto_commit_push) and
  reports the restored run's duration instead of ~0.
- **M2** — re-running a terminal (finished/failed/canceled) runner returns
  the cached result instead of crashing with a double-ValueError FSM error;
  ``_pre_run`` side effects are not re-executed.
- **H3** — ``run_if`` expressions are evaluated in a sandbox: imports, open,
  eval and dunder attribute access are rejected; expression-language and
  ``success()``/``failure()``/``canceled()``/``always()`` keep working.
- **L1** — the lifecycle stores metadata/context under the shared
  ``RunnerRegistryKeys`` members (stored strings stay ``"metadata"``/
  ``"context"``).
- **L12** — resolving a templated ``name`` invalidates the cached key prefix
  so registry keys never embed raw Jinja text.
- **L14** — runner construction no longer reconfigures global logging; the
  shared logger is resolved lazily on first use.
- **L3** — documents the deliberate fail-fast vs fail-soft split; tests on
  this file pin both behaviors.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ofx.runner import RunContext, RunnerStatus
from ofx.runner.lifecycle import LifecycleManager, RunnerStateMachine
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.runner import Runner


class _RunnerStub:
    """Minimal duck-typed runner used by lifecycle tests."""

    def __init__(self) -> None:
        self.run_id = "run-1"
        self.name = "runner"
        self.model = SimpleNamespace()
        self.ctx = RunContext()
        self.parent = None
        self._cached_durable_config = None
        self._state_machine = RunnerStateMachine()
        self._error = None
        self._registry = None
        self._warnings: list[str] = []
        self._debugs: list[str] = []
        self._cleanup_calls: list[str] = []
        self._started_at = None
        self._finished_at = None
        self._started_at_utc = None
        self._finished_at_utc = None

    async def reg_set_many(self, _items):
        return None

    async def _pre_run(self):
        return None

    async def _do_run(self):
        return None

    async def _post_run(self):
        return None

    async def _on_failure_cleanup(self):
        self._cleanup_calls.append("cleanup")

    async def get_result(self):
        return SimpleNamespace(status=RunnerStatus.COMPLETED, outputs={})

    def _log_warning(self, message: str) -> None:
        self._warnings.append(message)

    def _log_debug(self, message: str) -> None:
        self._debugs.append(message)

    @property
    def status(self):
        return self._state_machine.current_state


def _manager() -> LifecycleManager:
    return LifecycleManager(_RunnerStub())


# ---------------------------------------------------------------------------
# H1 — registry cleanup is root-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_execution_child_runner_does_not_close_shared_registry(
    monkeypatch,
) -> None:
    manager = _manager()
    shared_registry = object()
    manager._runner._registry = shared_registry
    manager._runner.parent = SimpleNamespace()  # child shares parent's registry
    manager._runner._error = "boom"
    manager._runner._state_machine.set_state(RunnerStatus.FAILED)
    events: list[str] = []
    cleaned: list[object] = []
    pushed: list[str] = []

    class _Emitter:
        def emit(self, event_type: str, payload=None) -> None:
            events.append(event_type)

    async def _write_final_checkpoints(_self):
        return None

    async def _cleanup_registry(registry):
        cleaned.append(registry)

    async def _auto_commit_push(_self):
        pushed.append("push")

    manager._event_emitter = _Emitter()
    monkeypatch.setattr(
        LifecycleManager, "_write_final_checkpoints", _write_final_checkpoints
    )
    monkeypatch.setattr(
        type(manager._checkpoint_manager), "auto_commit_push", _auto_commit_push
    )
    monkeypatch.setattr("ofx.runner.lifecycle.cleanup_registry", _cleanup_registry)

    await manager._finalize_execution()

    # A child runner must not close the registry it shares with its parent.
    assert cleaned == []
    assert events == ["runner_finish"]
    assert pushed == ["push"]


# ---------------------------------------------------------------------------
# M1 — durable resume participates in finalization and reports a duration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_resume_runs_finalization_and_reports_restored_duration(
    monkeypatch,
) -> None:
    manager = _manager()
    manager._runner._registry = object()
    manager._runner._state_machine.set_state(RunnerStatus.COMPLETED)
    events: list[str] = []
    cleaned: list[object] = []
    pushed: list[str] = []

    class _Emitter:
        def emit(self, event_type: str, payload=None) -> None:
            events.append(event_type)

    async def _restore(_self):
        # Mirrors CheckpointManager.restore_from_checkpoint: it restores the
        # original UTC timestamps and the terminal state.
        manager._runner._started_at_utc = "2026-01-01T00:00:00+00:00"
        manager._runner._finished_at_utc = "2026-01-01T00:01:00+00:00"
        return True

    async def _write_final_checkpoints(_self):
        return None

    async def _cleanup_registry(registry):
        cleaned.append(registry)

    async def _auto_commit_push(_self):
        pushed.append("push")

    manager._event_emitter = _Emitter()
    monkeypatch.setattr(
        type(manager._checkpoint_manager), "restore_from_checkpoint", _restore
    )
    monkeypatch.setattr(
        LifecycleManager, "_write_final_checkpoints", _write_final_checkpoints
    )
    monkeypatch.setattr(
        type(manager._checkpoint_manager), "auto_commit_push", _auto_commit_push
    )
    monkeypatch.setattr("ofx.runner.lifecycle.cleanup_registry", _cleanup_registry)

    await manager.execute()

    assert events == ["runner_start", "runner_resume", "runner_finish"]
    # Finalization runs on the resume path too: root registry cleanup and
    # auto-commit/push both happen.
    assert cleaned == [manager._runner._registry]
    assert pushed == ["push"]
    # mark_finish anchored the perf clock without clobbering the restored
    # finish timestamp, and duration reflects the original run window.
    assert manager._runner._finished_at is not None
    assert manager._runner._finished_at_utc == "2026-01-01T00:01:00+00:00"
    assert manager.duration_ms() == 60_000


@pytest.mark.asyncio
async def test_execute_resume_skips_run_side_effects(monkeypatch) -> None:
    manager = _manager()
    calls: list[str] = []

    async def _restore(_self):
        return True

    async def _reg_set_many(_items):
        calls.append("reg_set_many")

    async def _pre_run():
        calls.append("pre_run")

    async def _do_run():
        calls.append("do_run")

    async def _post_run():
        calls.append("post_run")

    monkeypatch.setattr(
        type(manager._checkpoint_manager), "restore_from_checkpoint", _restore
    )
    manager._runner.reg_set_many = _reg_set_many
    manager._runner._pre_run = _pre_run
    manager._runner._do_run = _do_run
    manager._runner._post_run = _post_run

    await manager.execute()

    # Resuming from a completed checkpoint must not re-register metadata nor
    # re-run the execution body (_pre_run side effects stay untouched).
    assert calls == []


# ---------------------------------------------------------------------------
# M2 — re-running a terminal runner returns the cached result
# ---------------------------------------------------------------------------


class _CountingModel(BaseModel):
    name: str = "m"


class _CountingRunner(Runner[_CountingModel]):
    def __init__(self) -> None:
        super().__init__(_CountingModel(), RunContext())
        self.pre_run_calls = 0

    async def _pre_run(self) -> None:
        self.pre_run_calls += 1

    async def _do_run(self) -> None:
        return None

    async def _post_run(self) -> None:
        return None


class _FailingRunner(Runner[_CountingModel]):
    def __init__(self) -> None:
        super().__init__(_CountingModel(), RunContext())

    async def _pre_run(self) -> None:
        return None

    async def _do_run(self) -> None:
        raise RuntimeError("boom")

    async def _post_run(self) -> None:
        return None


@pytest.mark.asyncio
async def test_rerun_completed_runner_returns_cached_result_without_crash() -> None:
    runner = _CountingRunner()

    first = await runner.run()
    assert first.status == RunnerStatus.COMPLETED
    assert runner.pre_run_calls == 1

    # Re-running a finished runner must be idempotent: cached result, no
    # double-ValueError FSM crash, and no repeated _pre_run side effects.
    second = await runner.run()
    assert second.status == RunnerStatus.COMPLETED
    assert second.run_id == first.run_id
    assert runner.pre_run_calls == 1


@pytest.mark.asyncio
async def test_rerun_failed_runner_returns_cached_result_without_crash() -> None:
    runner = _FailingRunner()

    first = await runner.run()
    assert first.status == RunnerStatus.FAILED
    assert first.error == "boom"

    second = await runner.run()
    assert second.status == RunnerStatus.FAILED
    assert second.error == "boom"


# ---------------------------------------------------------------------------
# H3 — run_if evaluation is sandboxed
# ---------------------------------------------------------------------------


def test_evaluate_run_if_rejects_arbitrary_code() -> None:
    runner = object.__new__(Runner)
    with pytest.raises(ValueError, match="Forbidden name"):
        Runner._evaluate_run_if(runner, "__import__('os').system('echo pwned')")
    with pytest.raises(ValueError, match="Forbidden name"):
        Runner._evaluate_run_if(runner, "open('/etc/passwd')")
    with pytest.raises(ValueError, match="Forbidden name"):
        Runner._evaluate_run_if(runner, "eval('1 + 1')")
    with pytest.raises(ValueError, match="Forbidden name"):
        Runner._evaluate_run_if(runner, "getattr(1, 'bit_length')")


def test_evaluate_run_if_rejects_dunder_attribute_access() -> None:
    runner = object.__new__(Runner)
    with pytest.raises(ValueError, match="Forbidden dunder"):
        Runner._evaluate_run_if(runner, "().__class__")


def test_evaluate_run_if_supports_run_if_context_callables() -> None:
    runner = object.__new__(Runner)
    ctx = {
        "success": lambda: True,
        "failure": lambda: False,
        "canceled": lambda: False,
        "always": lambda: True,
    }
    assert Runner._evaluate_run_if(runner, "success()", ctx) is True
    assert Runner._evaluate_run_if(runner, "failure()", ctx) is False
    assert Runner._evaluate_run_if(runner, "canceled()", ctx) is False
    assert Runner._evaluate_run_if(runner, "always()", ctx) is True


def test_evaluate_run_if_simple_values_and_expressions() -> None:
    runner = object.__new__(Runner)
    assert Runner._evaluate_run_if(runner, None) is True
    assert Runner._evaluate_run_if(runner, True) is True
    assert Runner._evaluate_run_if(runner, False) is False
    assert Runner._evaluate_run_if(runner, 0) is False
    assert Runner._evaluate_run_if(runner, 1) is True
    assert Runner._evaluate_run_if(runner, "1 == 1") is True
    assert Runner._evaluate_run_if(runner, "len('ab') == 2") is True


# ---------------------------------------------------------------------------
# L1 — lifecycle stores metadata/context under RunnerRegistryKeys members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_registers_metadata_and_context_via_registry_key_members() -> None:
    manager = _manager()
    manager._runner.ctx = RunContext(inputs={"a": 1}, secrets={"x": "y"}, envs={"A": "1"})
    recorded: list[dict[str, dict[str, object]]] = []

    async def _reg_set_many(items):
        recorded.append(items)

    manager._runner.reg_set_many = _reg_set_many

    await manager.execute()

    items = recorded[0]
    # Keys are the shared constants; stored strings remain "metadata"/"context".
    assert RunnerRegistryKeys.METADATA in items
    assert RunnerRegistryKeys.CONTEXT in items
    assert str(RunnerRegistryKeys.METADATA) == "metadata"
    assert str(RunnerRegistryKeys.CONTEXT) == "context"
    assert items[RunnerRegistryKeys.METADATA]["run_id"] == "run-1"
    assert "secrets" not in items[RunnerRegistryKeys.CONTEXT]
    assert "envs" not in items[RunnerRegistryKeys.CONTEXT]


# ---------------------------------------------------------------------------
# L12 — resolving a templated name invalidates the cached key prefix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_template_fields_invalidates_cached_key_prefix_for_name() -> None:
    class _NameRunner(Runner[_CountingModel]):
        def __init__(self) -> None:
            super().__init__(_CountingModel(), RunContext())
            self._resolve_template_calls = 0

        async def _pre_run(self) -> None: ...
        async def _do_run(self) -> None: ...
        async def _post_run(self) -> None: ...

        async def _resolve_template(self, _value, context_vars=None):
            self._resolve_template_calls += 1
            return "build-linux"

    runner = _NameRunner()
    # Runner.__init__ sets name = "[RUNNER][<run_id>]"; override to a raw
    # Jinja value, simulating a step/job name before resolution.
    runner.name = "build-{{ matrix.os }}"
    runner.model.name = "build-{{ matrix.os }}"
    runner._cached_key_prefix = None

    # First key lookup caches the prefix while the name is still raw Jinja.
    assert Runner._key_prefix(runner) == "_NameRunner:build-{{ matrix.os }}:"

    changed = await Runner._resolve_template_fields(runner, ["name"])
    assert changed is True
    assert runner.model.name == "build-linux"
    assert runner._resolve_template_calls == 1

    # A runner subclass syncs its display name from the resolved model
    # name (as happens after template resolution); the cached prefix must
    # be dropped so keys use the resolved name instead of raw Jinja text.
    runner.name = runner.model.name
    key = Runner.get_key(runner, "outputs")

    assert key == "_NameRunner:build-linux:outputs"
    assert "{{" not in key


# ---------------------------------------------------------------------------
# L14 — runner construction defers global logging reconfiguration
# ---------------------------------------------------------------------------


class _LoggingModel(BaseModel):
    name: str = "m"


class _LoggingRunner(Runner[_LoggingModel]):
    async def _pre_run(self) -> None: ...
    async def _do_run(self) -> None: ...
    async def _post_run(self) -> None: ...


def test_runner_construction_does_not_touch_global_logging(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("get_logger() must not run during Runner construction")

    monkeypatch.setattr("ofx.runner.runner.get_logger", _boom)

    runner = _LoggingRunner(_LoggingModel(), RunContext())

    # Construction succeeded without resolving the shared logger; the log
    # level is deferred until first actual use.
    assert runner._log_level is None


def test_runner_log_level_resolves_lazily_on_first_read(monkeypatch) -> None:
    import ofx.runner.runner as runner_module

    captured: list[str] = []
    real_get_logger = runner_module.get_logger

    def _spy():
        captured.append("resolved")
        return real_get_logger()

    monkeypatch.setattr("ofx.runner.runner.get_logger", _spy)

    runner = _LoggingRunner(_LoggingModel(), RunContext())
    assert captured == []  # construction did not resolve

    level = runner.log_level  # first read resolves
    assert captured == ["resolved"]
    assert isinstance(level, int)


def test_runner_logging_emits_after_lazy_init() -> None:
    import logging

    runner = _LoggingRunner(_LoggingModel(), RunContext())

    # Emitting through the deferred logger must work and respect the
    # runner's log level the same way as before the lazy change.
    assert runner.log_level > logging.DEBUG  # default effective level
    runner._log_debug("lazy logger debug message")  # must not raise
    runner._log_info("lazy logger info message")  # must not raise


# ---------------------------------------------------------------------------
# L3 — fail-fast vs fail-soft resolution contract (behavior pinned)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_template_field_failure_propagates_but_output_failure_is_soft() -> None:
    class _SoftModel(BaseModel):
        name: str = "wf"
        outputs: dict[str, str] = {"target": "{{ broken }}"}

    class _SoftRunner(Runner[_SoftModel]):
        async def _pre_run(self) -> None: ...
        async def _do_run(self) -> None: ...
        async def _post_run(self) -> None: ...

    runner = _SoftRunner(_SoftModel(), RunContext())
    warnings: list[str] = []
    runner._log_warning = warnings.append

    async def _fail_template(_value, context_vars=None):
        raise RuntimeError("template boom")

    runner._resolve_template = _fail_template

    # Fail-soft: an unresolvable *output* degrades to "" + warning, and the
    # run continues.
    resolved = await runner._resolve_job_outputs()
    assert resolved == {"target": ""}
    assert warnings == ["Failed to resolve output 'target': template boom"]

    # Fail-fast: an unresolvable *configuration field* propagates so the
    # runner cannot silently run with a broken config.
    with pytest.raises(RuntimeError, match="template boom"):
        await runner._resolve_template_fields(["name"])
