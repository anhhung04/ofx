"""Command step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.core.base import BaseRunner
from ofx.runner.handlers import get_handler_registry

registry = get_handler_registry()


@registry.register(RunType.COMMAND)
def _create_command_runner(step_runner) -> BaseRunner:
    from ofx.runner.commands.command import Command, CommandRunner

    is_interactive = step_runner.model.interactive and step_runner.ctx.allow_interactive
    assert step_runner.model.run is not None, "Run cannot be None for COMMAND run type"
    cmd = Command(
        cmd=step_runner.model.run,
        shell=step_runner.model.shell,
        working_directory=step_runner._resolve_working_dir(),
        timeout_minutes=step_runner.model.timeout,
        interactive=is_interactive,
    )
    return CommandRunner(
        cmd,
        step_runner._child_context(),
        parent=step_runner,
    )
