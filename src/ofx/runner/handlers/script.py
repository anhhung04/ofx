"""Script step handlers."""

from __future__ import annotations

from ofx.cloud.script_runtime import resolve_python_step_source
from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry
from ofx.runner.run_defaults import resolve_model_shell

@registry.register(RunType.SCRIPT, RunType.SCRIPT_FILE)
def create_runner(step_runner):
    """Create a ScriptRunner for inline and file-backed Python steps."""
    from ofx.runner.commands.command import Script, ScriptRunner

    model = Script(
        shell=resolve_model_shell(step_runner, step_runner.model),
        working_directory=step_runner._resolve_working_dir(),
        script=resolve_python_step_source(
            step_runner.model,
            workflow_dir=step_runner.ctx.workflow_dir,
        ),
        timeout_minutes=step_runner.model.timeout,
        interactive=step_runner.model.interactive,
    )
    return ScriptRunner(
        model,
        context_copy(step_runner.ctx),
        parent=step_runner,
    )
