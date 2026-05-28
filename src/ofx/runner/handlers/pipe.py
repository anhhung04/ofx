"""Pipe step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.handlers.registry import registry
from ofx.runner.handlers.shared import build_child_runner


@registry.register(RunType.PIPE)
def _create_pipe_runner(step_runner):
    """Build a PipeRunner from the step's pipe configuration."""
    from ofx.runner.pipe import PipeExecution, PipeRunner

    assert step_runner.model.pipe is not None, (
        "pipe cannot be None for PIPE run type"
    )

    model = PipeExecution(pipe=step_runner.model.pipe)
    return build_child_runner(
        model,
        PipeRunner,
        step_runner,
    )
