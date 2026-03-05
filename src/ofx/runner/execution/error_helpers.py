"""Shared error formatting helpers for runners."""

from __future__ import annotations

from typing import Any


def step_execution_error(status: Any, error: Any) -> str:
    return f"Step execution failed with status: {status}, error: {error}"


def step_timeout_error(timeout_minutes: int) -> str:
    return f"Step timed out after {timeout_minutes} minutes."


def step_retry_error(max_attempts: int, error: Any) -> str:
    return f"Step failed after {max_attempts} attempts:\n{error}"


def job_step_failed(step_name_or_index: Any, error: Any) -> str:
    return f"Step '{step_name_or_index}' failed: {error}"


def extract_root_error(error: str | None) -> str:
    """Extract the most meaningful error from a nested error chain.

    The runner hierarchy wraps errors at each level (step → job → workflow).
    This strips the wrapper prefixes to show only the root cause.
    """
    if not error:
        return "Unknown error"

    # Walk through known wrapper patterns and strip them
    lines = error.strip().splitlines()
    # Find the deepest meaningful line (skip wrapper prefixes)
    for line in reversed(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("Job failure") and not stripped.startswith("===="):
            return stripped
    return lines[-1].strip() if lines else error
