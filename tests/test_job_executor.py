"""Tests for job executor cleanup behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ofx.runner.executors.job import JobExecutor
from ofx.runner.registry_keys import RunnerRegistryKeys


class _PreRunRunner:
    def __init__(self) -> None:
        from ofx.runner import RunContext

        self.ctx = RunContext(envs={"BASE": "1"})
        self.model = SimpleNamespace(
            env={"CHILD": "2"},
            model_dump=lambda exclude=None: {"jid": "job-1", "env": {"CHILD": "2"}},
        )
        self.resolved_fields: list[list[str]] = []
        self.logs: list[str] = []
        self.registry_updates: list[tuple[str, dict]] = []

    async def _resolve_template_fields(self, fields):
        self.resolved_fields.append(list(fields))

    def _log_debug(self, message: str) -> None:
        self.logs.append(message)

    async def reg_set(self, key: str, value: dict) -> None:
        self.registry_updates.append((key, value))


class _StepRunner:
    def __init__(self, output_file: str = "", error: Exception | None = None) -> None:
        self.output_file = output_file
        self.error = error

    async def get_result(self):
        if self.error:
            raise self.error
        return SimpleNamespace(outputs={"output_file": self.output_file})


class _Runner:
    def __init__(self, step_runners) -> None:
        self._runners = dict(enumerate(step_runners))
        self.model = SimpleNamespace(jid="job-1")
        self.logs: list[str] = []

    def _log_debug(self, message: str) -> None:
        self.logs.append(message)


@pytest.mark.asyncio
async def test_prepare_job_context_resolves_fields_and_merges_env():
    runner = _PreRunRunner()

    await JobExecutor()._prepare_job_context(runner)

    assert runner.resolved_fields == [["name", "needs", "run_if", "env", "defaults"]]
    assert runner.ctx.envs["BASE"] == "1"
    assert runner.ctx.envs["CHILD"] == "2"
    assert runner.logs == ["Resolved job: {'jid': 'job-1', 'env': {'CHILD': '2'}}"]


@pytest.mark.asyncio
async def test_store_job_model_persists_registry_shape():
    runner = _PreRunRunner()

    await JobExecutor()._store_job_model(runner)

    assert runner.registry_updates == [(
        RunnerRegistryKeys.MODEL,
        {"jid": "job-1", "env": {"CHILD": "2"}},
    )]


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_removes_task_output(tmp_path):
    output = tmp_path / ".ofx_task_output.json"
    output.write_text("{}")
    runner = _Runner([_StepRunner(str(output))])

    await JobExecutor().cleanup_temp_task_files(runner)

    assert not output.exists()
    assert runner.logs == []


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_keeps_non_task_output(tmp_path):
    output = tmp_path / "task-output.json"
    output.write_text("{}")
    runner = _Runner([_StepRunner(str(output))])

    await JobExecutor().cleanup_temp_task_files(runner)

    assert output.exists()
    assert runner.logs == []


@pytest.mark.asyncio
async def test_cleanup_temp_task_files_logs_result_lookup_failure(tmp_path):
    output = tmp_path / ".ofx_task_output.json"
    output.write_text("{}")
    runner = _Runner(
        [
            _StepRunner(error=RuntimeError("missing result")),
            _StepRunner(str(output)),
        ]
    )

    await JobExecutor().cleanup_temp_task_files(runner)

    assert not output.exists()
    assert runner.logs == [
        "Job 'job-1': failed to read step result for temp task cleanup: "
        "missing result"
    ]


def test_cleanup_temp_task_output_logs_invalid_path() -> None:
    runner = _Runner([])

    JobExecutor()._cleanup_temp_task_output(runner, "bad\0.ofx_task_output.json")

    assert len(runner.logs) == 1
    assert runner.logs[0].startswith(
        "Job 'job-1': invalid temp task output path "
        "'bad\x00.ofx_task_output.json':"
    )
