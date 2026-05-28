"""Shared helpers for resolving inherited runner execution defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.settings import DEFAULT_SHELL


def model_field_is_explicitly_set(model: Any, field: str) -> bool:
    """Return whether a pydantic-backed model field was explicitly provided."""
    return field in getattr(model, "model_fields_set", set())


def resolve_parent_run_default(runner: Any, field: str) -> Any | None:
    """Return the nearest inherited ``defaults.run.<field>`` value."""
    parent = getattr(runner, "parent", None)
    while parent is not None:
        model = getattr(parent, "model", None)
        defaults = getattr(model, "defaults", None)
        run_defaults = getattr(defaults, "run", None)
        value = getattr(run_defaults, field, None)
        if value is not None:
            return value
        parent = getattr(parent, "parent", None)
    return None


def resolve_model_run_default(
    runner: Any,
    model: Any,
    field: str,
    *,
    fallback: Any,
) -> Any:
    """Resolve a model field from explicit state, inherited defaults, or fallback."""
    if model_field_is_explicitly_set(model, field):
        return getattr(model, field)
    return resolve_parent_run_default(runner, field) or fallback


def resolve_model_shell(runner: Any, model: Any) -> str:
    """Resolve shell from explicit model state or inherited run defaults."""
    return resolve_model_run_default(
        runner,
        model,
        "shell",
        fallback=DEFAULT_SHELL,
    )


def resolve_model_working_directory(runner: Any, model: Any) -> Path:
    """Resolve working directory from explicit model state or inherited defaults."""
    return resolve_model_run_default(
        runner,
        model,
        "working_directory",
        fallback=Path.cwd(),
    )


__all__ = [
    "model_field_is_explicitly_set",
    "resolve_model_run_default",
    "resolve_model_shell",
    "resolve_model_working_directory",
    "resolve_parent_run_default",
]
