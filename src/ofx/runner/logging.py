"""Structured logging helpers for runner components."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from ofx.settings import settings
from ofx.utils.log import reload_logging_config

_logger: logging.Logger | None = None


@dataclass(frozen=True)
class LogContext:
    """Structured metadata attached to runner log records."""

    run_id: str | None = None
    runner_type: str | None = None
    runner_name: str | None = None
    model_name: str | None = None
    model_jid: str | None = None
    step_index: int | str | None = None
    status: str | None = None
    parent_run_id: str | None = None

    @property
    def prefix(self) -> str:
        parts: list[str] = []
        if self.run_id:
            parts.append(f"[RUN-{self.run_id}]")
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
        model = getattr(runner, "model", None)
        status = getattr(getattr(runner, "status", None), "value", None)
        parent = getattr(runner, "parent", None)
        return cls(
            run_id=getattr(runner, "run_id", None),
            runner_type=type(runner).__name__,
            runner_name=getattr(runner, "name", None),
            model_name=getattr(model, "name", None),
            model_jid=getattr(model, "jid", None),
            step_index=getattr(model, "step_index", None),
            status=status,
            parent_run_id=getattr(parent, "run_id", None),
        )


class StructuredLogger:
    """Thin adapter that emits runner logs with structured context."""

    def __init__(self, runner: Any, logger: logging.Logger | None = None) -> None:
        self._runner = runner
        self._logger = logger or get_logger()

    def context(self) -> LogContext:
        return LogContext.from_runner(self._runner)

    def _extra(self) -> dict[str, Any]:
        return {"log_context": asdict(self.context())}

    def _message(self, message: Any) -> str:
        context = self.context()
        prefix = context.prefix
        text = str(message)
        return f"{prefix} | {text}" if prefix else text

    def debug(self, message: Any) -> None:
        self._logger.debug(self._message(message), extra=self._extra())

    def info(self, message: Any) -> None:
        self._logger.info(self._message(message), extra=self._extra())

    def warning(self, message: Any) -> None:
        self._logger.warning(self._message(message), extra=self._extra())

    def error(self, message: Any) -> None:
        self._logger.error(self._message(message), extra=self._extra())


def bubble_log(parent: Any, message: str) -> str:
    """Delegate a child runner log message to its parent when present."""
    if parent is not None:
        return parent._produce_log(message)
    return message


def bubble_context_log(parent: Any, message: Any, **context_fields: Any) -> str:
    """Format a message from log context fields and bubble it to the parent."""
    prefix = LogContext(**context_fields).prefix
    text = str(message)
    formatted = f"{prefix} › {text}" if prefix else text
    return bubble_log(parent, formatted)


def bubble_tagged_log(
    parent: Any,
    message: Any,
    *,
    prefix: str = "",
    tags: tuple[str, ...] = (),
) -> str:
    """Format a message with bracketed tags and bubble it to the parent."""
    text = str(message)
    tag_text = " ".join(f"[{tag}]" for tag in tags if tag)
    head = " ".join(part for part in (prefix, tag_text) if part)
    formatted = f"{head} › {text}" if head else text
    return bubble_log(parent, formatted)


def prefix_log(message: Any, prefix: str) -> str:
    """Format a message with a simple text prefix."""
    return f"{prefix} {message}"


def get_logger() -> logging.Logger:
    """Return the shared OFX logger instance."""

    global _logger
    if _logger is None:
        _logger = logging.getLogger(settings.app_branding)
        reload_logging_config(settings)
    return _logger


__all__ = [
    "LogContext",
    "StructuredLogger",
    "bubble_context_log",
    "bubble_log",
    "bubble_tagged_log",
    "get_logger",
    "prefix_log",
]
