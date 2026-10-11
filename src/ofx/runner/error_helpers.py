"""Shared error formatting helpers for runners."""

from __future__ import annotations

from typing import Any


def coerce_timeout_minutes(value: int | str) -> int:
    """Coerce a template-resolved timeout value to minutes."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 60 * 24

def step_execution_error(status: Any, error: Any) -> str:
    """Format a failed step result (what failed, why, how to proceed).

    The leading ``"Step execution failed with status: <status>, error: ..."``
    fragment is relied upon by retry logging, so it stays first; the
    remediation lines are appended after it.
    """
    return (
        f"Step execution failed with status: {status}, error: {error}\n"
        f"Why: the step's command or module exited without reaching a "
        f"completed status.\n"
        f"Remediation: check the step's stdout/stderr above and fix the "
        f"reported error, or set 'continue-on-error: true' on the step to "
        f"let the workflow proceed."
    )

def step_timeout_error(timeout_minutes: int) -> str:
    return (
        f"Step timed out after {timeout_minutes} minute(s).\n"
        f"Why: the step did not finish within its 'timeout' budget "
        f"({timeout_minutes} minute(s)).\n"
        f"Remediation: raise 'timeout' in the step definition "
        f"(e.g. 'timeout: {timeout_minutes * 2}'), or make the step faster."
    )

def step_retry_error(max_attempts: int, error: Any) -> str:
    return (
        f"Step failed after {max_attempts} attempt(s).\n"
        f"Last error: {error}\n"
        f"Why: every attempt failed, so retries are exhausted.\n"
        f"Remediation: if the failure is transient, increase 'retry' "
        f"(and optionally 'retry-delay'); otherwise fix the root cause "
        f"before re-running."
    )

def job_step_failed(step_name_or_index: Any, error: Any) -> str:
    return (
        f"Step '{step_name_or_index}' failed: {error}\n"
        f"Why: the step reported a failed status, and a failed step aborts "
        f"its job unless 'continue-on-error: true' is set on it.\n"
        f"Remediation: check the step's logs for the cause and re-run; set "
        f"'continue-on-error: true' on the step to let the job proceed, or "
        f"'retry: <n>' to retry it automatically."
    )

def job_failure_summary(job_id: str, error: str | None) -> str:
    """Format a job failure line for the CLI error summary."""
    root = extract_root_error(error)
    return f"  job '{job_id}': {root}"

def extract_root_error(error: str | None) -> str:
    """Extract the most meaningful error from a nested error chain.

    The runner hierarchy wraps errors at each level (step -> job -> workflow).
    This strips the wrapper prefixes to show only the root cause.
    """
    if not error:
        return "Unknown error"

    lines = error.strip().splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("Job failure")
            and not stripped.startswith("====")
        ):
            return stripped
    return lines[-1].strip() if lines else error

__all__ = [
    "coerce_timeout_minutes",
    "extract_root_error",
    "job_failure_summary",
    "job_step_failed",
    "step_execution_error",
    "step_retry_error",
    "step_timeout_error",
]
