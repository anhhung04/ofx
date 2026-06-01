"""Tests for job executor cleanup behavior."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ofx.runner import RunContext
from ofx.runner.context import ConditionNotMetError, RunnerStatus
from ofx.runner.executors.job import JobExecutor
from ofx.runner.registry_keys import RunnerRegistryKeys


@pytest.mark.asyncio
async def test_do_run_registers_and_configures_local_step_runners(monkeypatch):
    captured = []
    logs: list[str] = []

    monkeypatch.setattr(
        "ofx.runner.step.StepRunner",
        lambda step, ctx, parent: (
            captured.append((step.step_index, ctx, parent))
            or SimpleNamespace(
                is_failed=False,
                log_level=None,
                run=AsyncMock(return_value=SimpleNamespace(error=None)),
            )
        ),
    )

    runner = SimpleNamespace(
        ctx=RunContext(secrets={"token": "secret"}),
        model=SimpleNamespace(
            name="Job Name",
            jid="job-1",
            steps=[
                SimpleNamespace(
                    step_index=0,
                    secrets="inherit",
                    continue_on_error=False,
                    name="step-0",
                ),
                SimpleNamespace(
                    step_index=1,
                    secrets={"any": "value"},
                    continue_on_error=True,
                    name="step-1",
                )
            ],
        ),
        _runners={},
        _log_info=logs.append,
    )
    await JobExecutor().do_run(runner)

    assert list(runner._runners) == ["0", "1"]
    assert runner._runners["0"].log_level == logging.CRITICAL
    assert captured[0][0] == 0
    assert captured[0][2] is runner
    assert captured[0][1].secrets == {"token": "secret"}
    assert captured[1][0] == 1
    assert captured[1][1].secrets == {}
    assert logs == ["Starting job 'Job Name'"]


@pytest.mark.asyncio
async def test_do_run_raises_for_failed_step(monkeypatch):
    monkeypatch.setattr(
        "ofx.runner.step.StepRunner",
        lambda _step, _ctx, _parent: SimpleNamespace(
            is_failed=True,
            log_level=None,
            run=AsyncMock(return_value=SimpleNamespace(error="boom")),
        ),
    )

    with pytest.raises(RuntimeError, match="step-1"):
        await JobExecutor().do_run(
            SimpleNamespace(
                ctx=RunContext(),
                model=SimpleNamespace(
                    name="Job Name",
                    jid="job-1",
                    steps=[
                        SimpleNamespace(
                            step_index=1,
                            secrets={},
                            continue_on_error=False,
                            name="step-1",
                        )
                    ],
                ),
                _runners={},
                _log_info=lambda _message: None,
            )
        )


@pytest.mark.asyncio
async def test_pre_run_resolves_fields_merges_env_and_stores_model(monkeypatch):
    resolved_fields: list[list[str]] = []
    logs: list[str] = []
    registry_updates: list[tuple[str, dict]] = []
    state_transitions: list[object] = []

    async def _resolve_template_fields(fields):
        resolved_fields.append(list(fields))

    async def reg_set(key: str, value: dict) -> None:
        registry_updates.append((key, value))

    runner = SimpleNamespace(
        ctx=RunContext(envs={"BASE": "1"}),
        parent=SimpleNamespace(
            model=SimpleNamespace(
                defaults=SimpleNamespace(
                    model_dump=lambda: {
                        "run": {"working_directory": ".", "shell": "bash"},
                        "workflows_base_dir": ".",
                        "flow_registry_url": "https://github.com",
                        "durable": {
                            "enabled": True,
                            "resume": True,
                            "backend": "file",
                            "redis_prefix": "ofx:durable:",
                            "auto_commit": False,
                            "auto_push": False,
                        },
                        "profile": "",
                        "store_creds": False,
                    }
                )
            )
        ),
        model=SimpleNamespace(
            env={"CHILD": "2"},
            defaults=SimpleNamespace(
                model_dump=lambda exclude_defaults=False: {"run": {"shell": "zsh"}}
            ),
            model_dump=lambda exclude=None: {"jid": "job-1", "env": {"CHILD": "2"}},
            needs=[],
            run_if=True,
        ),
        resolved_fields=resolved_fields,
        logs=logs,
        registry_updates=registry_updates,
        state_transitions=state_transitions,
        _state_machine=SimpleNamespace(transition=state_transitions.append),
        _resolve_template_fields=_resolve_template_fields,
        _log_debug=logs.append,
        reg_set=reg_set,
    )
    runner.update_env = lambda env: runner.ctx.envs.update(env)

    executor = JobExecutor()

    monkeypatch.setattr(executor, "check_dependencies_and_run_if", lambda _runner: None)

    await executor.pre_run(runner)

    assert runner.resolved_fields == [["name", "needs", "run_if", "env", "defaults"]]
    assert runner.ctx.envs["BASE"] == "1"
    assert runner.ctx.envs["CHILD"] == "2"
    assert runner.model.defaults.model_dump()["run"]["shell"] == "zsh"
    assert runner.model.defaults.model_dump()["run"]["working_directory"] == Path(".")
    assert runner.logs == ["Resolved job: {'jid': 'job-1', 'env': {'CHILD': '2'}}"]
    assert runner.registry_updates == [(
        RunnerRegistryKeys.MODEL,
        {"jid": "job-1", "env": {"CHILD": "2"}},
    )]

def test_check_dependencies_and_run_if_normalizes_string_needs_and_defaults_run_if() -> None:
    dep_runner = SimpleNamespace(
        is_success=True,
        is_failed=False,
        status=RunnerStatus.COMPLETED,
    )
    captured: list[tuple[object, dict[str, object]]] = []
    runner = SimpleNamespace(
        model=SimpleNamespace(needs="build", run_if=True),
        parent=SimpleNamespace(runners={"build": dep_runner}),
        _evaluate_run_if=lambda expr, ctx: captured.append((expr, ctx)) or True,
    )

    JobExecutor().check_dependencies_and_run_if(runner)

    assert runner.model.needs == ["build"]
    assert captured[0][0] == "success()"


def test_check_dependencies_and_run_if_raises_for_missing_dependency() -> None:
    runner = SimpleNamespace(
        model=SimpleNamespace(needs=["build"], run_if=True),
        parent=SimpleNamespace(runners={}),
    )

    with pytest.raises(RuntimeError, match="Job dependency 'build' is missing"):
        JobExecutor().check_dependencies_and_run_if(runner)


def test_check_dependencies_and_run_if_cancels_when_condition_fails() -> None:
    dep_runner = SimpleNamespace(is_success=False, is_failed=True, status=RunnerStatus.FAILED)
    runner = SimpleNamespace(
        model=SimpleNamespace(needs=["build"], run_if="failure()"),
        parent=SimpleNamespace(runners={"build": dep_runner}),
        _state_machine=SimpleNamespace(transition=lambda status: transitions.append(status)),
        _evaluate_run_if=lambda _expr, _ctx: False,
        _produce_log=lambda message: f"wrapped: {message}",
    )
    transitions: list[RunnerStatus] = []

    with pytest.raises(ConditionNotMetError, match="wrapped: Job condition is not met"):
        JobExecutor().check_dependencies_and_run_if(runner)

    assert transitions == [RunnerStatus.CANCELED]


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_removes_task_output(tmp_path):
    output = tmp_path / ".ofx_task_output.json"
    output.write_text("{}")
    logs: list[str] = []
    runner = SimpleNamespace(
        _runners={
            0: SimpleNamespace(
                get_result=AsyncMock(
                    return_value=SimpleNamespace(outputs={"output_file": str(output)})
                )
            )
        },
        model=SimpleNamespace(jid="job-1"),
        logs=logs,
        _log_debug=logs.append,
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert not output.exists()
    assert runner.logs == []


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_keeps_non_task_output(tmp_path):
    output = tmp_path / "task-output.json"
    output.write_text("{}")
    logs: list[str] = []
    runner = SimpleNamespace(
        _runners={
            0: SimpleNamespace(
                get_result=AsyncMock(
                    return_value=SimpleNamespace(outputs={"output_file": str(output)})
                )
            )
        },
        model=SimpleNamespace(jid="job-1"),
        logs=logs,
        _log_debug=logs.append,
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert output.exists()
    assert runner.logs == []


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_logs_result_lookup_failure(tmp_path):
    output = tmp_path / ".ofx_task_output.json"
    output.write_text("{}")
    logs: list[str] = []
    runner = SimpleNamespace(
        _runners={
            0: SimpleNamespace(get_result=AsyncMock(side_effect=RuntimeError("missing result"))),
            1: SimpleNamespace(
                get_result=AsyncMock(
                    return_value=SimpleNamespace(outputs={"output_file": str(output)})
                )
            ),
        },
        model=SimpleNamespace(jid="job-1"),
        logs=logs,
        _log_debug=logs.append,
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert not output.exists()
    assert runner.logs == [
        "Job 'job-1': failed to read step result for temp task cleanup: "
        "missing result"
    ]


@pytest.mark.asyncio
async def test_execute_steps_registers_suffix_and_allows_continue_on_error(monkeypatch) -> None:
    step = SimpleNamespace(step_index=2, continue_on_error=True, name="step-2")
    runner = SimpleNamespace(ctx=RunContext(), model=SimpleNamespace(steps=[step]), _runners={})

    monkeypatch.setattr(
        "ofx.runner.step.StepRunner",
        lambda _step, _step_ctx, _runner: SimpleNamespace(
            is_failed=True,
            log_level=None,
            run=AsyncMock(return_value=SimpleNamespace(error="boom")),
        ),
    )

    await JobExecutor()._execute_steps(
        runner,
        suffix="_a",
    )

    step_runner = runner._runners["2_a"]
    assert list(runner._runners) == ["2_a"]
    assert step_runner.log_level == logging.CRITICAL
@pytest.mark.asyncio
async def test_cleanup_temp_task_files_logs_invalid_temp_output_path() -> None:
    logs: list[str] = []
    runner = SimpleNamespace(
        _runners={
            0: SimpleNamespace(
                get_result=AsyncMock(
                    return_value=SimpleNamespace(outputs={"output_file": "bad\0.ofx_task_output.json"})
                )
            )
        },
        model=SimpleNamespace(jid="job-1"),
        logs=logs,
        _log_debug=logs.append,
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert len(runner.logs) == 1
    assert runner.logs[0].startswith(
        "Job 'job-1': invalid temp task output path "
        "'bad\x00.ofx_task_output.json':"
    )


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_logs_remove_failure(monkeypatch) -> None:
    logs: list[str] = []
    runner = SimpleNamespace(
        _runners={
            0: SimpleNamespace(
                get_result=AsyncMock(
                    return_value=SimpleNamespace(outputs={"output_file": "/tmp/.ofx_task_output.json"})
                )
            )
        },
        model=SimpleNamespace(jid="job-1"),
        logs=logs,
        _log_debug=logs.append,
    )

    monkeypatch.setattr(
        "ofx.runner.executors.job.remove_file",
        lambda *_args, **_kwargs: OSError("boom"),
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert runner.logs == [
        "Job 'job-1': failed to remove temp task file '/tmp/.ofx_task_output.json': boom"
    ]
