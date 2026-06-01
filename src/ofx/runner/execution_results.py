"""Structured execution results for runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ofx.runner.context import RunnerStatus, normalized_runner_status_value
from ofx.runner.metadata import ModelContext

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StepExecutionResult:
    step_index: int
    name: str
    run_type: str
    status: str
    error: str | None
    outputs: dict[str, Any]
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobExecutionResult:
    jid: str
    name: str
    status: str
    error: str | None
    total_steps: int
    failed_steps: list[int]
    steps: list[dict[str, Any]]
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_step_execution_result_for_runner(
    step_runner: Any,
    *,
    status: str,
    error: str | None,
    outputs: dict[str, Any],
) -> StepExecutionResult:
    """Build a step execution result directly from a step-like runner."""
    model = getattr(step_runner, "model", None)
    model_context = ModelContext.from_model(model)
    if model is None or model_context.step_index is None:
        raise ValueError("Runner does not contain step metadata")

    run_type = getattr(step_runner, "_run_type", None)
    return StepExecutionResult(
        step_index=model_context.step_index,
        name=model_context.name,
        run_type=run_type.value if run_type is not None else model.get_run_type().value,
        status=status,
        error=error,
        outputs=outputs,
        duration_ms=step_runner.duration_ms(),
    )


def build_job_execution_result(
    runner: Any,
    step_runners: dict[str, Any],
) -> JobExecutionResult:
    """Build a JobExecutionResult from a job runner and its step runners.

    Shared between JobRunner and CloudJobRunner to avoid duplication.
    """
    step_results: list[dict[str, Any]] = []
    failed_steps: list[int] = []
    for step_runner in step_runners.values():
        try:
            step_result = build_step_execution_result_for_runner(
                step_runner,
                status=normalized_runner_status_value(step_runner.status),
                error=getattr(step_runner, "_error", None),
                outputs={},
            ).to_dict()
        except ValueError:
            continue
        step_results.append(step_result)
        if step_result["status"] == RunnerStatus.FAILED.value:
            failed_steps.append(step_result["step_index"])

    return JobExecutionResult(
        jid=runner.model.jid,
        name=runner.model.name,
        status=normalized_runner_status_value(runner.status),
        error=runner._error,
        total_steps=len(runner.model.steps),
        failed_steps=failed_steps,
        steps=step_results,
        duration_ms=runner.duration_ms(),
    )


def build_run_if_context(dep_runners: list[Any]) -> dict[str, Any]:
    """Build the run_if evaluation context for a job runner.

    Shared between JobRunner, CloudJobRunner, MatrixJobRunner.
    """
    success = True if not dep_runners else all(r.is_success for r in dep_runners)
    failure = False if not dep_runners else any(r.is_failed for r in dep_runners)
    canceled = False if not dep_runners else any(
        r.status == RunnerStatus.CANCELED for r in dep_runners
    )
    return {
        "success": lambda: success,
        "failure": lambda: failure,
        "canceled": lambda: canceled,
        "always": lambda: True,
    }
