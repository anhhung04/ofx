"""Command step handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ofx.models.step import RunType
from ofx.runner.handlers.registry import registry
from ofx.runner.handlers.shared import (
    build_child_runner,
    resolved_execution_model_kwargs,
)

if TYPE_CHECKING:
    from ofx.runner.runner import BaseRunner


@registry.register(RunType.COMMAND)
def _create_command_runner(step_runner) -> BaseRunner:
    from ofx.runner.commands.command import Command, CommandRunner

    is_interactive = step_runner.model.interactive and step_runner.ctx.allow_interactive
    assert step_runner.model.run is not None, "Run cannot be None for COMMAND run type"
    cmd = Command(
        cmd=step_runner.model.run,
        **resolved_execution_model_kwargs(step_runner),
        timeout_minutes=step_runner.model.timeout,
        interactive=is_interactive,
    )
    return build_child_runner(
        cmd,
        CommandRunner,
        step_runner,
    )
