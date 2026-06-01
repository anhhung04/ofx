"""Pipe step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry


@registry.register(RunType.PIPE)
def create_runner(step_runner):
    """Build a PipeRunner from the step's pipe configuration."""
    from ofx.runner.pipe import PipeExecution, PipeRunner

    assert step_runner.model.pipe is not None, (
        "pipe cannot be None for PIPE run type"
    )

    model = PipeExecution(pipe=step_runner.model.pipe)
    return PipeRunner(
        model,
        context_copy(step_runner.ctx),
        parent=step_runner,
    )
