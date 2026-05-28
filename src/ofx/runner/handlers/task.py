"""Task step handler."""

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


@registry.register(RunType.TASK)
def _create_task_runner(step_runner) -> BaseRunner:
    from ofx.runner.task_step import extract_task_target_and_opts
    from ofx.runner.tasks.runner import TaskExecution, TaskRunner

    assert step_runner.model.task is not None, (
        "task cannot be None for TASK run type"
    )
    target, task_opts = extract_task_target_and_opts(step_runner.model.run_with)
    if not target:
        step_runner._log_warning(
            f"Task '{step_runner.model.task}' has no 'target' in 'with:' - "
            "the tool may fail or scan nothing."
        )
    task_model = TaskExecution(
        task_name=step_runner.model.task,
        target=target,
        opts=task_opts,
        **resolved_execution_model_kwargs(step_runner),
        timeout_minutes=step_runner.model.timeout,
        store_creds=step_runner._resolve_store_creds(),
    )
    return build_child_runner(
        task_model,
        TaskRunner,
        step_runner,
    )
