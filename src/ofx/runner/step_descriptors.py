"""Shared helpers for describing workflow step sources."""

from __future__ import annotations

from typing import Any

_STEP_SOURCE_FIELDS: tuple[tuple[str, str], ...] = (
    ("uses", "workflow"),
    ("script", "script"),
    ("script_file", "script_file"),
    ("run", "command"),
)

_STEP_LABEL_PREFIXES: dict[str, str] = {
    "workflow": "uses: ",
    "script_file": "script_file: ",
    "pipe": "pipe: → ",
}

_STEP_HEADER_PREFIXES: dict[str, str] = {
    "command": ">> command: ",
    "workflow": ">> workflow: ",
    "script_file": ">> script_file: ",
}

_TIMELINE_COMMAND_PREFIXES: dict[str, str] = {
    "script": "script:",
    "workflow": "uses:",
    "script_file": "script_file:",
    "pipe": "pipe:",
}

def step_source_kind_and_value(step: Any) -> tuple[str, Any]:
    """Return a normalized `(kind, value)` pair for a workflow step."""
    if getattr(step, "pipe", None) is not None:
        pipe = step.pipe
        return "pipe", getattr(pipe, "format", "json")

    for field_name, kind in _STEP_SOURCE_FIELDS:
        value = getattr(step, field_name, None)
        if value:
            return kind, value
    return "unknown", None

def step_type_label(step: Any, *, command_preview_chars: int = 60) -> str:
    """Return a human-readable summary label for a workflow step."""
    kind, value = step_source_kind_and_value(step)
    if kind == "command":
        lines = str(value).strip().splitlines()
        first = lines[0][:command_preview_chars]
        if len(lines) > 1 or len(lines[0]) > command_preview_chars:
            first += "…"
        return f"run: {first}"
    if kind == "script":
        return "script"
    if kind in _STEP_LABEL_PREFIXES:
        return f"{_STEP_LABEL_PREFIXES[kind]}{value}"
    return "unknown"

def step_timeline_params(
    step: Any,
    *,
    outputs: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return normalized `(command, tool, target)` timeline metadata."""
    outputs = outputs or {}
    kind, value = step_source_kind_and_value(step)

    if kind == "command":
        command = str(value or "")
        tool = ""
        target = ""
    elif kind in _TIMELINE_COMMAND_PREFIXES:
        if kind in {"script", "pipe"}:
            suffix = getattr(step, "name", None) or "inline"
        else:
            suffix = value or ""
        command = f"{_TIMELINE_COMMAND_PREFIXES[kind]}{suffix}"
        tool = ""
        target = ""
    else:
        command = ""
        tool = ""
        target = ""

    return {
        "command": command,
        "tool": tool,
        "target": target,
    }

__all__ = [
    "step_timeline_params",
    "step_source_kind_and_value",
    "step_type_label",
]
