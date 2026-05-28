"""Reusable workflow step handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ofx.models.step import RunType
from ofx.runner.handlers.registry import registry
from ofx.runner.handlers.shared import build_child_runner

if TYPE_CHECKING:
    from ofx.runner.runner import BaseRunner


@registry.register(RunType.WORKFLOW)
def _create_workflow_runner(step_runner) -> BaseRunner:
    from ofx.runner.workflow import WorkflowRunner
    from ofx.utils.workflow_utils import find_workflow, workflow_dirs_with_path

    workflow_dirs = workflow_dirs_with_path(
        step_runner.ctx.workflow_dirs,
        step_runner.ctx.workflow_dir or step_runner.parent.model.workflow_path.parent,
    )
    workflow = find_workflow(
        step_runner.model.uses or "",
        tuple(workflow_dirs),
        step_runner.parent.model.defaults.flow_registry_url,
    )
    return build_child_runner(
        workflow,
        WorkflowRunner,
        step_runner,
        context_update={
            "workflow_dirs": workflow_dirs_with_path(
                workflow_dirs, workflow.workflow_path.parent
            ),
        },
    )
