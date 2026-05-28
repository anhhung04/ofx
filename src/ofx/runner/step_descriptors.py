"""Shared helpers for describing workflow step sources."""

from __future__ import annotations

import base64
from typing import Any


def step_source_kind_and_value(step: Any) -> tuple[str, Any]:
    """Return a normalized `(kind, value)` pair for a workflow step."""
    if getattr(step, "task", None):
        return "task", step.task
    if getattr(step, "uses", None):
        return "workflow", step.uses
    if getattr(step, "script", None):
        return "script", step.script
    if getattr(step, "script_file", None):
        return "script_file", step.script_file
    if getattr(step, "pipe", None) is not None:
        pipe = step.pipe
        return "pipe", getattr(pipe, "format", "json")
    if getattr(step, "run", None):
        return "command", step.run
    return "unknown", None


def step_type_label(step: Any, *, command_preview_chars: int = 60) -> str:
    """Return a human-readable summary label for a workflow step."""
    kind, value = step_source_kind_and_value(step)
    if kind == "task":
        return f"task: {value}"
    if kind == "workflow":
        return f"uses: {value}"
    if kind == "script":
        return "script"
    if kind == "script_file":
        return f"script_file: {value}"
    if kind == "pipe":
        return f"pipe: → {value}"
    if kind == "command":
        lines = str(value).strip().splitlines()
        first = lines[0][:command_preview_chars]
        if len(lines) > 1 or len(lines[0]) > command_preview_chars:
            first += "…"
        return f"run: {first}"
    return "unknown"


def step_output_header_line(step: Any) -> str:
    """Return the leading metadata line for a saved step output log."""
    kind, value = step_source_kind_and_value(step)
    if kind == "command":
        return f">> command: {value}"
    if kind == "workflow":
        return f">> workflow: {value}"
    if kind == "script_file":
        return f">> script_file: {value}"
    if kind == "script":
        encoded = base64.b64encode(str(value).encode()).decode()
        return f">> script (base64): {encoded}"
    if kind == "task":
        return f">> task: {value}"
    return ">> unknown step type"


def step_timeline_params(
    step: Any,
    *,
    outputs: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return normalized `(command, tool, target)` timeline metadata."""
    outputs = outputs or {}
    kind, value = step_source_kind_and_value(step)
    if kind == "command":
        return {"command": str(value or ""), "tool": "", "target": ""}
    if kind == "task":
        from ofx.runner.task_step import extract_task_target_and_opts

        task_name = str(value or "")
        target, _ = extract_task_target_and_opts(getattr(step, "run_with", {}))
        command = str(outputs.get("command", f"task:{task_name}"))
        return {"command": command, "tool": task_name, "target": target}
    if kind == "script":
        return {"command": f"script:{getattr(step, 'name', None) or 'inline'}", "tool": "", "target": ""}
    if kind == "script_file":
        return {"command": f"script_file:{value or ''}", "tool": "", "target": ""}
    if kind == "workflow":
        return {"command": f"uses:{value or ''}", "tool": "", "target": ""}
    if kind == "pipe":
        return {"command": f"pipe:{getattr(step, 'name', None) or 'inline'}", "tool": "", "target": ""}
    return {"command": "", "tool": "", "target": ""}


__all__ = [
    "step_timeline_params",
    "step_output_header_line",
    "step_source_kind_and_value",
    "step_type_label",
]
