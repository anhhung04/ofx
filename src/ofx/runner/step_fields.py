"""Shared template-field lists for step runners."""

from __future__ import annotations

from ofx.models.step import RunType

BASE_STEP_TEMPLATE_FIELDS: tuple[str, ...] = (
    "name",
    "shell",
    "working_directory",
    "log_stdout",
    "log_command",
    "env",
    "run_if",
)

RUN_TYPE_TEMPLATE_FIELDS: dict[RunType, list[str]] = {
    RunType.WORKFLOW: ["uses"],
    RunType.SCRIPT: ["script"],
    RunType.COMMAND: ["run"],
    RunType.SCRIPT_FILE: ["script_file"],
    RunType.PIPE: [],
}

__all__ = ["BASE_STEP_TEMPLATE_FIELDS", "RUN_TYPE_TEMPLATE_FIELDS"]
