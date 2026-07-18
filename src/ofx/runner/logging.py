"""Structured logging helpers for runner components."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from ofx.runner.context import normalized_runner_status_value
from ofx.runner.metadata import ModelContext
from ofx.settings import settings
from ofx.utils.log import reload_logging_config

_logger: logging.Logger | None = None

@dataclass(frozen=True)
class LogContext:
    """Structured metadata attached to runner log records."""

    run_id: str | None = None
    runner_type: str | None = None
    model_name: str | None = None
    model_jid: str | None = None
    step_index: int | str | None = None
    status: str | None = None
    parent_run_id: str | None = None

    @property
    def prefix(self) -> str:
        parts: list[str] = []
        if self.runner_type:
            parts.append(self.runner_type)
        if self.model_name:
            parts.append(f"name={self.model_name}")
        if self.model_jid:
            parts.append(f"job={self.model_jid}")
        if self.step_index is not None:
            parts.append(f"step={self.step_index}")
        if self.status:
            parts.append(f"status={self.status}")
        return " | ".join(parts)

    @classmethod
    def from_runner(cls, runner: Any) -> LogContext:
        model_context = ModelContext.from_model(getattr(runner, "model", None))
        status_obj = getattr(runner, "status", None)
        status = (
            normalized_runner_status_value(status_obj)
            if status_obj is not None
            else None
        )
        parent = getattr(runner, "parent", None)
        return cls(
            run_id=getattr(runner, "run_id", None),
            runner_type=type(runner).__name__,
            model_name=model_context.name,
            model_jid=model_context.jid,
            step_index=model_context.step_index,
            status=status,
            parent_run_id=getattr(parent, "run_id", None),
        )

class StructuredLogger:
    """Thin adapter that emits runner logs with structured context."""

    def __init__(self, runner: Any, logger: logging.Logger | None = None) -> None:
        self._runner = runner
        self._logger = logger or get_logger()

    def format_message(
        self,
        message: Any,
        context: LogContext | None = None,
    ) -> str:
        context = context or LogContext.from_runner(self._runner)
        text = str(message)
        return f"{context.prefix} | {text}" if context.prefix else text

    def _log(self, level_name: str, message: Any) -> None:
        context = LogContext.from_runner(self._runner)
        getattr(self._logger, level_name)(
            self.format_message(message, context),
            extra={"log_context": asdict(context)},
        )

    def debug(self, message: Any) -> None:
        self._log("debug", message)

    def info(self, message: Any) -> None:
        self._log("info", message)

    def warning(self, message: Any) -> None:
        self._log("warning", message)

    def error(self, message: Any) -> None:
        self._log("error", message)

def bubble_context_log(parent: Any, message: Any, **context_fields: Any) -> str:
    """Format a message from log context fields and bubble it to the parent."""
    head = LogContext(**context_fields).prefix
    text = str(message)
    formatted = f"{head} › {text}" if head else text
    if parent is not None:
        return parent._produce_log(formatted)
    return formatted

def get_logger() -> logging.Logger:
    """Return the shared OFX logger instance."""

    global _logger
    if _logger is None:
        _logger = logging.getLogger(settings.app_branding)
        reload_logging_config(settings)
    return _logger

__all__ = [
    "LogContext",
    "ModelContext",
    "StructuredLogger",
    "bubble_context_log",
    "get_logger",
]
