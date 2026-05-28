"""Script step handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ofx.cloud.script_runtime import resolve_python_step_source
from ofx.models.step import RunType
from ofx.runner.handlers.registry import registry
from ofx.runner.handlers.shared import (
    build_child_runner,
    resolved_execution_model_kwargs,
)

if TYPE_CHECKING:
    from ofx.runner.runner import BaseRunner


def _build_script_runner(step_runner) -> BaseRunner:
    """Create a ScriptRunner for inline and file-backed Python steps."""
    from ofx.runner.commands.command import Script, ScriptRunner

    script_model = Script(
        script=resolve_python_step_source(
            step_runner.model,
            workflow_dir=step_runner.ctx.workflow_dir,
        ),
        **resolved_execution_model_kwargs(step_runner),
        timeout_minutes=step_runner.model.timeout,
        interactive=step_runner.model.interactive,
    )
    return build_child_runner(
        script_model,
        ScriptRunner,
        step_runner,
    )


@registry.register(RunType.SCRIPT, RunType.SCRIPT_FILE)
def _create_script_runner(step_runner) -> BaseRunner:
    return _build_script_runner(step_runner)


_create_script_file_runner = _create_script_runner
