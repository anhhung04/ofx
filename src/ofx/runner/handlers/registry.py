"""Registry for step run-type handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from ofx.models.step import RunType

class SupportsStepHandler(Protocol):
    """Protocol describing the step runner API required by handlers."""

    model: object
    ctx: object
    parent: object
    _run_type: RunType

    def _log_warning(self, message: str) -> None: ...
    def _log_info(self, message: str) -> None: ...
    def _resolve_working_dir(self): ...

StepHandlerT = TypeVar("StepHandlerT", bound=Callable[[SupportsStepHandler], Any])

class HandlerRegistry:
    """Map [`RunType`](src/ofx/models/step.py) values to runner factory callables."""

    def __init__(self) -> None:
        self._handlers: dict[RunType, Callable[[SupportsStepHandler], Any]] = {}

    def register(self, *run_types: RunType) -> Callable[[StepHandlerT], StepHandlerT]:
        """Register a handler factory for one or more run types."""
        if not run_types:
            raise ValueError("At least one run type must be provided")

        def decorator(handler: StepHandlerT) -> StepHandlerT:
            for run_type in run_types:
                self._handlers[run_type] = handler
            return handler

        return decorator

    def get(self, run_type: RunType) -> Callable[[SupportsStepHandler], Any]:
        """Return the registered handler factory for *run_type*."""
        handler = self._handlers.get(run_type)
        if handler is None:
            raise ValueError(f"Invalid run type '{run_type}'. No handler registered.")
        return handler

registry = HandlerRegistry()

__all__ = ["HandlerRegistry", "registry"]
