"""Task step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.context import context_copy
from ofx.runner.handlers.registry import registry
from ofx.runner.run_defaults import resolve_model_shell


@registry.register(RunType.TASK)
def create_runner(step_runner):
    from ofx.runner.task_step import extract_task_target_and_opts
    from ofx.runner.tasks.runner import TaskExecution, TaskRunner
    from ofx.runner.services.credential_store import should_store_creds

    assert step_runner.model.task is not None, (
        "task cannot be None for TASK run type"
    )
    target, task_opts = extract_task_target_and_opts(step_runner.model.run_with)
    if not target:
        step_runner._log_warning(
            f"Task '{step_runner.model.task}' has no 'target' in 'with:' - "
            "the tool may fail or scan nothing."
        )
    model = TaskExecution(
        shell=resolve_model_shell(step_runner, step_runner.model),
        working_directory=step_runner._resolve_working_dir(),
        task_name=step_runner.model.task,
        target=target,
        opts=task_opts,
        timeout_minutes=step_runner.model.timeout,
        store_creds=should_store_creds(
            step_runner.model.store_creds,
            step_runner.parent.model if step_runner.parent else None,
        ),
    )
    return TaskRunner(
        model,
        context_copy(step_runner.ctx),
        parent=step_runner,
    )
