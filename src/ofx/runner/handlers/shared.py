"""Shared helpers for step handler model construction."""

from __future__ import annotations

from typing import Any


def resolved_execution_model_kwargs(step_runner) -> dict[str, Any]:
    """Return shell and working-directory defaults resolved for a step runner."""
    return {
        "shell": step_runner._resolve_shell(),
        "working_directory": step_runner._resolve_working_dir(),
    }


def build_child_runner(
    model,
    runner_cls,
    step_runner,
    *,
    context_update: dict[str, Any] | None = None,
):
    """Instantiate a child runner with the step runner as parent."""
    return runner_cls(
        model,
        step_runner._child_context(update=context_update),
        parent=step_runner,
    )


__all__ = ["build_child_runner", "resolved_execution_model_kwargs"]
