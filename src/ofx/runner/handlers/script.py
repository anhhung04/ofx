"""Script step handlers."""

from __future__ import annotations

from pathlib import Path

from ofx.models.step import RunType
from ofx.runner.core.base import BaseRunner
from ofx.runner.handlers import get_handler_registry

registry = get_handler_registry()


@registry.register(RunType.SCRIPT)
def _create_script_runner(step_runner) -> BaseRunner:
    from ofx.runner.commands.command import Script, ScriptRunner

    assert step_runner.model.script is not None, (
        "Script cannot be None for SCRIPT run type"
    )
    script_model = Script(
        script=step_runner.model.script,
        shell=step_runner.model.shell,
        working_directory=step_runner.model.working_directory,
        timeout_minutes=step_runner.model.timeout,
        interactive=step_runner.model.interactive,
    )
    return ScriptRunner(
        script_model,
        step_runner._child_context(),
        parent=step_runner,
    )


@registry.register(RunType.SCRIPT_FILE)
def _create_script_file_runner(step_runner) -> BaseRunner:
    from ofx.runner.commands.command import Script, ScriptRunner

    assert step_runner.model.script_file is not None, (
        "script_file cannot be None for SCRIPT_FILE run type"
    )
    script_path = (
        Path(step_runner.model.script_file.strip()).expanduser().with_suffix(".py")
    )
    if not script_path.is_absolute():
        base_dir = getattr(step_runner.ctx, "workflow_dir", Path.cwd())
        script_path = (base_dir / script_path).resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script file '{script_path}' does not exist.")
    script_content = script_path.read_text()
    script_model = Script(
        script=script_content,
        shell=step_runner.model.shell,
        working_directory=step_runner.model.working_directory,
        timeout_minutes=step_runner.model.timeout,
        interactive=step_runner.model.interactive,
    )
    return ScriptRunner(
        script_model,
        step_runner._child_context(),
        parent=step_runner,
    )
