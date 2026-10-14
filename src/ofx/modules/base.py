"""Core types for the OFX module execution system."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MODULE_FUNCTION = "run"
"""Entry function used when a module spec omits an explicit ``::<func>``."""

PYTHON_MODULE_REQUIRES_SCRIPT = (
    "python module requires 'script' or 'script_file' in args"
)
"""Shared error text for python module steps with no script source."""


@dataclass(slots=True)
class ModuleContext:
    """Context passed to user-defined functions (UDFs) and builtin modules."""

    inputs: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, Any] = field(default_factory=dict)
    env: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    working_directory: Path = field(default_factory=Path.cwd)
    workflow_dir: Path | None = None
    """Directory of the currently executing workflow (relative assets)."""
    logger: Callable[[str], None] | logging.Logger | None = None
    add_outputs: Callable[..., None] | None = None
    publish: Callable[..., Any] | None = None
    subscribe: Callable[..., Any] | None = None
    wait_for: Callable[..., Any] | None = None
    scope_models: tuple[Any, Any, Any] | None = None
    """``(workflow_model, job_model, step_model)`` for python scripts."""
    channels_dir: Path | None = None
    """Directory used by the channel store (``None`` when unconfigured)."""
    interactive: bool = False
    """Whether interactive mode is allowed (step model + ctx.allow_interactive)."""

    def log(self, message: str) -> None:
        """Log a message through the step logger (no-op if unset)."""
        if self.logger is None:
            return
        if isinstance(self.logger, logging.Logger):
            self.logger.info(message)
        else:
            self.logger(message)


@dataclass(slots=True)
class ModuleResult:
    """Result of a module invocation."""

    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    result: Any | None = None
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    """Resolution of a module name to a callable and metadata."""

    kind: str
    name: str
    description: str = ""
    args_schema: dict[str, Any] = field(default_factory=dict)
    callable: Callable[..., Any] | None = None
    file: Path | None = None
    function: str | None = None


__all__ = [
    "DEFAULT_MODULE_FUNCTION",
    "PYTHON_MODULE_REQUIRES_SCRIPT",
    "ModuleContext",
    "ModuleResult",
    "ModuleSpec",
]
