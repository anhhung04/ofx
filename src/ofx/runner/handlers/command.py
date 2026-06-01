"""Command step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry
from ofx.runner.run_defaults import resolve_model_shell


@registry.register(RunType.COMMAND)
def create_runner(step_runner):
    from ofx.runner.commands.command import Command, CommandRunner

    is_interactive = step_runner.model.interactive and step_runner.ctx.allow_interactive
    assert step_runner.model.run is not None, "Run cannot be None for COMMAND run type"
    model = Command(
        shell=resolve_model_shell(step_runner, step_runner.model),
        working_directory=step_runner._resolve_working_dir(),
        cmd=step_runner.model.run,
        timeout_minutes=step_runner.model.timeout,
        interactive=is_interactive,
    )
    return CommandRunner(
        model,
        context_copy(step_runner.ctx),
        parent=step_runner,
    )
