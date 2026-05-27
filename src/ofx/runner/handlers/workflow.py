"""Reusable workflow step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.core.base import BaseRunner
from ofx.runner.handlers import get_handler_registry

registry = get_handler_registry()


@registry.register(RunType.WORKFLOW)
def _create_workflow_runner(step_runner) -> BaseRunner:
    from ofx.runner.execution.workflow import WorkflowRunner
    from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

    workflow_dirs = (
        step_runner.ctx.workflow_dirs.copy() if step_runner.ctx.workflow_dirs else []
    )
    workflow = find_workflow(
        step_runner.model.uses or "",
        tuple(workflow_dirs),
        step_runner.parent.model.defaults.flow_registry_url,
    )
    return WorkflowRunner(
        workflow,
        step_runner._child_context(
            update={
                "workflow_dirs": add_workflow_dir(
                    workflow_dirs, workflow.workflow_path.parent
                ),
            }
        ),
        parent=step_runner,
    )
