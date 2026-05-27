"""Pipe step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.core.base import BaseRunner
from ofx.runner.handlers import get_handler_registry

registry = get_handler_registry()


@registry.register(RunType.PIPE)
def _create_pipe_runner(step_runner) -> BaseRunner:
    """Build a PipeRunner from the step's pipe configuration."""
    from ofx.runner.execution.pipe import PipeExecution, PipeRunner

    assert step_runner.model.pipe is not None, (
        "pipe cannot be None for PIPE run type"
    )

    model = PipeExecution(pipe=step_runner.model.pipe)
    return PipeRunner(
        model,
        step_runner._child_context(),
        parent=step_runner,
    )
