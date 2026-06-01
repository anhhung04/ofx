"""Tests for step executor orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.models.step import RunType
from ofx.runner.context import RunnerStatus
from ofx.runner.executors.step import StepExecutor
from ofx.runner.registry_keys import RunnerRegistryKeys


@pytest.mark.asyncio
async def test_store_step_execution_persists_execution_payload() -> None:
    recorded: list[tuple[str, dict]] = []

    runner = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2"),
        _run_type=SimpleNamespace(value="command"),
        duration_ms=lambda: 25,
        reg_set=AsyncMock(side_effect=lambda key, value: recorded.append((key, value))),
    )

    await StepExecutor()._store_step_execution(
        runner,
        status=RunnerStatus.COMPLETED.value,
        error=None,
        outputs={"stdout": "ok"},
    )

    assert recorded == [
        (
            RunnerRegistryKeys.EXECUTION,
            {
                "step_index": 2,
                "name": "step-2",
                "run_type": "command",
                "status": "completed",
                "error": None,
                "outputs": {"stdout": "ok"},
                "duration_ms": 25,
            },
        )
    ]


@pytest.mark.asyncio
async def test_post_run_persists_normalized_execution_and_cleans_outputs(tmp_path) -> None:
    recorded: list[tuple[str, dict]] = []
    emitted: list[object] = []
    outputs_file = tmp_path / "step.out"
    outputs_file.write_text("data")

    runner = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2", log_command=False),
        _run_type=SimpleNamespace(value="command"),
        _outputs_file=outputs_file,
        ctx=SimpleNamespace(vars={}),
        duration_ms=lambda: 25,
        reg_set=AsyncMock(side_effect=lambda key, value: recorded.append((key, value))),
        get_result=AsyncMock(
            return_value=SimpleNamespace(
                status=RunnerStatus.FINISHED,
                error=None,
                outputs={"stdout": "ok"},
            )
        ),
        _emit_result_outputs=emitted.append,
    )

    await StepExecutor().post_run(runner)

    assert emitted and emitted[0].outputs == {"stdout": "ok"}
    assert recorded[0][0] == RunnerRegistryKeys.EXECUTION
    assert recorded[0][1]["status"] == "completed"
    assert not outputs_file.exists()


@pytest.mark.asyncio
async def test_post_run_logs_timeline_when_log_command_enabled(tmp_path, monkeypatch) -> None:
    recorded: list[tuple[str, dict]] = []
    outputs_file = tmp_path / "step.out"
    outputs_file.write_text("data")
    timeline_calls: list[dict[str, object]] = []

    runner = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2", log_command=True),
        _run_type=SimpleNamespace(value="command"),
        _outputs_file=outputs_file,
        ctx=SimpleNamespace(vars={"project": "demo"}),
        duration_ms=lambda: 25,
        reg_set=AsyncMock(side_effect=lambda key, value: recorded.append((key, value))),
        get_result=AsyncMock(
            return_value=SimpleNamespace(
                status=RunnerStatus.FINISHED,
                error=None,
                outputs={"stdout": "ok", "exit_code": 3},
            )
        ),
        _emit_result_outputs=lambda _result: None,
        _build_timeline_params=lambda _result: {"source_host": "host-a", "tags": "cloud"},
    )

    monkeypatch.setattr(
        "ofx.runner.timeline.log_step",
        lambda **kwargs: timeline_calls.append(kwargs),
    )

    await StepExecutor().post_run(runner)

    assert recorded[0][0] == RunnerRegistryKeys.EXECUTION
    assert timeline_calls == [{
        "ctx_vars": {"project": "demo"},
        "step_name": "step-2",
        "status": "completed",
        "duration_ms": 25,
        "exit_code": 3,
        "source_host": "host-a",
        "tags": "cloud",
    }]
    assert not outputs_file.exists()


@pytest.mark.asyncio
async def test_on_failure_persists_failure_execution_and_cleans_outputs(tmp_path) -> None:
    recorded: list[tuple[str, dict]] = []
    outputs_file = tmp_path / "step.err"
    outputs_file.write_text("data")

    runner = SimpleNamespace(
        model=SimpleNamespace(step_index=2, name="step-2"),
        _run_type=SimpleNamespace(value="command"),
        _outputs_file=outputs_file,
        _error="fallback-error",
        duration_ms=lambda: 25,
        reg_set=AsyncMock(side_effect=lambda key, value: recorded.append((key, value))),
        get_result=AsyncMock(
            return_value=SimpleNamespace(
                status=RunnerStatus.FAILED,
                error=None,
                outputs={"stderr": "boom"},
            )
        ),
        _log_debug=lambda _message: None,
    )

    await StepExecutor().on_failure(runner)

    assert recorded[0][0] == RunnerRegistryKeys.EXECUTION
    assert recorded[0][1]["status"] == "failed"
    assert recorded[0][1]["error"] == "fallback-error"
    assert not outputs_file.exists()


@pytest.mark.asyncio
async def test_do_run_retries_then_succeeds(monkeypatch) -> None:
    calls: list[str] = []
    sleep_delays: list[float] = []

    def _completed_result():
        return SimpleNamespace(
            status=RunnerStatus.COMPLETED,
            error=None,
            outputs={"ok": True},
            model_dump=lambda exclude=None: {"status": RunnerStatus.COMPLETED, "error": None},
        )

    created_runners = iter(
        [
            SimpleNamespace(
                is_success=False,
                run=AsyncMock(
                    return_value=SimpleNamespace(
                        status=RunnerStatus.FAILED,
                        error="boom",
                        outputs={},
                    )
                ),
            ),
            SimpleNamespace(is_success=True, run=AsyncMock(return_value=_completed_result())),
        ]
    )
    runner = SimpleNamespace(
        model=SimpleNamespace(retry=1, timeout=1, retry_delay=2, name="step-2", step_index=2),
        ctx=SimpleNamespace(vars={}),
        _run_type=SimpleNamespace(value="command"),
        _retry_delay_seconds=lambda *, attempt, base_delay: (
            0.5 if (attempt, base_delay) == (0, 2) else None
        ),
        _log_info=calls.append,
        _log_debug=calls.append,
        reg_set=AsyncMock(),
        get_result=AsyncMock(return_value=SimpleNamespace(status=RunnerStatus.COMPLETED)),
        _create_runner=lambda: next(created_runners),
    )

    monkeypatch.setattr(
        "asyncio.sleep",
        AsyncMock(side_effect=lambda delay: sleep_delays.append(delay)),
    )

    await StepExecutor().do_run(runner)

    assert sleep_delays == [0.5]
    assert calls[0] == (
        "Retry 2/2 in 0.5s - Step execution failed with status: "
        "RunnerStatus.FAILED, error: boom"
    )
    assert calls[-1] == "result: namespace(status=<RunnerStatus.COMPLETED: 'completed'>)"


@pytest.mark.asyncio
async def test_do_run_raises_after_final_retry(monkeypatch) -> None:
    sleep_delays: list[float] = []

    runner = SimpleNamespace(
        model=SimpleNamespace(retry=1, timeout=1, retry_delay=2, name="step-2", step_index=2),
        _retry_delay_seconds=lambda *, attempt, base_delay: 0.5,
        _log_info=lambda _message: None,
        reg_set=AsyncMock(),
        _create_runner=lambda: SimpleNamespace(
            is_success=False,
            run=AsyncMock(
                return_value=SimpleNamespace(
                    status=RunnerStatus.FAILED,
                    error="boom",
                    outputs={},
                    model_dump=lambda exclude=None: {"status": RunnerStatus.FAILED, "error": "boom"},
                )
            ),
        ),
    )

    monkeypatch.setattr(
        "asyncio.sleep",
        AsyncMock(side_effect=lambda delay: sleep_delays.append(delay)),
    )

    with pytest.raises(RuntimeError, match=r"failed after 2 attempt\(s\)"):
        await StepExecutor().do_run(runner)

    assert sleep_delays == [0.5]


@pytest.mark.asyncio
async def test_do_run_warns_and_uses_registry_for_workflow_interactive_step() -> None:
    warnings: list[str] = []
    results: list[tuple[str, dict]] = []
    created: list[object] = []

    child_runner = SimpleNamespace(
        is_success=True,
        run=AsyncMock(
            return_value=SimpleNamespace(
                status=RunnerStatus.COMPLETED,
                error=None,
                outputs={"ok": True},
                model_dump=lambda exclude=None: {"status": RunnerStatus.COMPLETED, "error": None},
            )
        ),
    )
    runner = SimpleNamespace(
        model=SimpleNamespace(
            retry=0,
            timeout=1,
            retry_delay=2,
            name="step-2",
            step_index=2,
            interactive=True,
        ),
        ctx=SimpleNamespace(vars={}, allow_interactive=True),
        _run_type=RunType.WORKFLOW,
        _handler_registry=SimpleNamespace(
            get=lambda run_type: (
                (lambda current_runner: created.append(current_runner) or child_runner)
                if run_type == RunType.WORKFLOW
                else None
            )
        ),
        _log_warning=warnings.append,
        _log_debug=lambda _message: None,
        reg_set=AsyncMock(side_effect=lambda key, value: results.append((key, value))),
        get_result=AsyncMock(return_value=SimpleNamespace(status=RunnerStatus.COMPLETED)),
    )

    await StepExecutor().do_run(runner)

    assert created == [runner]
    assert warnings == [
        "Interactive mode is not supported for workflow steps ('uses'). Ignoring interactive flag."
    ]
    assert [key for key, _value in results] == [RunnerRegistryKeys.OUTPUTS, RunnerRegistryKeys.RESULT]
