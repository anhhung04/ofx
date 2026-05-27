"""Step handler registry mapping RunType to handler factory functions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ofx.models.step import RunType

if TYPE_CHECKING:
    from ofx.runner.core.base import BaseRunner
    from ofx.runner.execution.step import StepRunner

StepHandlerFn = Callable[["StepRunner"], "BaseRunner"]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[RunType, StepHandlerFn] = {}

    def register(self, run_type: RunType) -> Callable[[StepHandlerFn], StepHandlerFn]:
        def decorator(fn: StepHandlerFn) -> StepHandlerFn:
            self._handlers[run_type] = fn
            return fn

        return decorator

    def get(self, run_type: RunType) -> StepHandlerFn:
        handler = self._handlers.get(run_type)
        if handler is None:
            raise ValueError(f"Invalid run type '{run_type}'. No handler registered.")
        return handler

    def create(self, run_type: RunType, step_runner: "StepRunner") -> "BaseRunner":
        return self.get(run_type)(step_runner)


_registry = HandlerRegistry()


def get_handler_registry() -> HandlerRegistry:
    return _registry


from ofx.runner.handlers import command as _command  # noqa: F401,E402
from ofx.runner.handlers import pipe as _pipe  # noqa: F401,E402
from ofx.runner.handlers import script as _script  # noqa: F401,E402
from ofx.runner.handlers import task as _task  # noqa: F401,E402
from ofx.runner.handlers import workflow as _workflow  # noqa: F401,E402
