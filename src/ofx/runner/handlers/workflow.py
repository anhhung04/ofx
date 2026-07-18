"""Reusable workflow step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry

@registry.register(RunType.WORKFLOW)
def create_runner(step_runner):
    from ofx.runner.workflow import WorkflowRunner
    from ofx.utils.workflow_utils import find_workflow, workflow_dirs_with_path

    parent_workflow_dir = (
        step_runner.ctx.workflow_dir
        or step_runner.parent.model.workflow_path.parent
    )
    search_dirs = workflow_dirs_with_path(
        step_runner.ctx.workflow_dirs,
        parent_workflow_dir,
    )
    workflow = find_workflow(
        step_runner.model.uses or "",
        tuple(search_dirs),
        step_runner.parent.model.defaults.flow_registry_url,
    )
    return WorkflowRunner(
        workflow,
        context_copy(
            step_runner.ctx,
            update={
                "workflow_dirs": workflow_dirs_with_path(
                    search_dirs, workflow.workflow_path.parent
                ),
            },
        ),
        parent=step_runner,
    )
