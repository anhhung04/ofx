"""Structured execution results for runners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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


# ---------------------------------------------------------------------------
# Shared helpers for building results (used by JobRunner + CloudJobRunner)
# ---------------------------------------------------------------------------


def build_job_execution_result(
    runner: Any,
    step_runners: dict[str, Any],
) -> JobExecutionResult:
    """Build a JobExecutionResult from a job runner and its step runners.

    Shared between JobRunner and CloudJobRunner to avoid duplication.
    """
    from ofx.runner.context import RunnerStatus as RS

    step_results: list[dict[str, Any]] = []
    failed_steps: list[int] = []

    for sr in step_runners.values():
        if not hasattr(sr, "model") or not hasattr(sr.model, "step_index"):
            continue
        # get_result is async so we use the sync cache via _error / status
        run_type = (
            sr._run_type.value
            if hasattr(sr, "_run_type") and sr._run_type
            else sr.model.get_run_type().value
        )
        status_val = RS.COMPLETED.value if sr.status == RS.FINISHED else sr.status.value
        step_exec = StepExecutionResult(
            step_index=sr.model.step_index,
            name=sr.model.name,
            run_type=run_type,
            status=status_val,
            error=sr._error,
            outputs={},
            duration_ms=sr.duration_ms(),
        )
        step_results.append(step_exec.to_dict())
        if sr.status == RS.FAILED:
            failed_steps.append(sr.model.step_index)

    status_value = (
        RS.COMPLETED.value if runner.status == RS.FINISHED else runner.status.value
    )
    return JobExecutionResult(
        jid=runner.model.jid,
        name=runner.model.name,
        status=status_value,
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
    from ofx.runner.context import RunnerStatus as RS

    if not dep_runners:
        return {
            "success": lambda: True,
            "failure": lambda: False,
            "canceled": lambda: False,
            "always": lambda: True,
        }
    return {
        "success": lambda: all(r.is_success for r in dep_runners),
        "failure": lambda: any(r.is_failed for r in dep_runners),
        "canceled": lambda: any(r.status == RS.CANCELED for r in dep_runners),
        "always": lambda: True,
    }


def build_step_execution_result(
    *,
    step_index: int,
    name: str,
    run_type: str,
    status: str,
    error: str | None,
    outputs: dict[str, Any],
    duration_ms: int | None,
) -> StepExecutionResult:
    """Build a StepExecutionResult consistently across step runners."""
    return StepExecutionResult(
        step_index=step_index,
        name=name,
        run_type=run_type,
        status=status,
        error=error,
        outputs=outputs,
        duration_ms=duration_ms,
    )
