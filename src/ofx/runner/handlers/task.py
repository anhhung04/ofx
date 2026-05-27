"""Task step handler."""

from __future__ import annotations

from ofx.models.step import RunType
from ofx.runner.core.base import BaseRunner
from ofx.runner.handlers import get_handler_registry

registry = get_handler_registry()


@registry.register(RunType.TASK)
def _create_task_runner(step_runner) -> BaseRunner:
    from ofx.runner.tasks.runner import TaskExecution, TaskRunner

    assert step_runner.model.task is not None, (
        "task cannot be None for TASK run type"
    )
    task_opts = dict(step_runner.model.run_with)
    raw_target = task_opts.pop("target", task_opts.pop("targets", ""))
    if isinstance(raw_target, list):
        target = ",".join(str(t) for t in raw_target)
    else:
        target = str(raw_target)
    if not target:
        step_runner._log_warning(
            f"Task '{step_runner.model.task}' has no 'target' in 'with:' - "
            "the tool may fail or scan nothing."
        )
    task_model = TaskExecution(
        task_name=step_runner.model.task,
        target=target,
        opts=task_opts,
        shell=step_runner.model.shell,
        working_directory=step_runner._resolve_working_dir(),
        timeout_minutes=step_runner.model.timeout,
        store_creds=step_runner._resolve_store_creds(),
    )
    return TaskRunner(
        task_model,
        step_runner._child_context(),
        parent=step_runner,
    )
