"""Shared error formatting helpers for runners."""

from __future__ import annotations

from typing import Any


def step_execution_error(status: Any, error: Any) -> str:
    return f"Step execution failed with status: {status}, error: {error}"


def step_timeout_error(timeout_minutes: int) -> str:
    return f"Step timed out after {timeout_minutes} minutes."


def step_retry_error(max_attempts: int, error: Any) -> str:
    return f"Step failed after {max_attempts} attempts. Error: {error}"


def job_step_failed(step_name_or_index: Any, error: Any) -> str:
    return f"Step '{step_name_or_index}' failed: {error}"
