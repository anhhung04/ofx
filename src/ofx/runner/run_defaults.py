"""Shared helpers for resolving inherited runner execution defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.settings import DEFAULT_SHELL


def model_field_is_explicitly_set(model: Any, field: str) -> bool:
    """Return whether a pydantic-backed model field was explicitly provided."""
    return field in getattr(model, "model_fields_set", set())


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

    parent = getattr(runner, "parent", None)
    while parent is not None:
        parent_model = getattr(parent, "model", None)
        defaults = getattr(parent_model, "defaults", None)
        run_defaults = getattr(defaults, "run", None)
        inherited = getattr(run_defaults, field, None)
        if inherited is not None:
            return inherited
        parent = getattr(parent, "parent", None)

    return fallback


def resolve_model_shell(runner: Any, model: Any) -> str:
    """Resolve shell from explicit model state or inherited run defaults."""
    return resolve_model_run_default(
        runner,
        model,
        "shell",
        fallback=DEFAULT_SHELL,
    )


__all__ = [
    "model_field_is_explicitly_set",
    "resolve_model_run_default",
    "resolve_model_shell",
]
