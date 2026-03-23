"""Shared task-step command helpers for cloud runner and sessions."""

from __future__ import annotations

from ofx.models.step import Step


def build_task_command_from_step(step: Step) -> str:
    """Build a shell command for a ``task:`` workflow step."""
    from ofx.tasks.registry import TaskRegistry

    if not step.task:
        raise RuntimeError("Task step is missing task name")

    task_cls = TaskRegistry.get(step.task)
    if task_cls is None:
        raise RuntimeError(f"Task '{step.task}' is not registered")

    task = task_cls()

    task_opts = dict(step.run_with)
    target = str(task_opts.pop("target", task_opts.pop("targets", "")))

    saved_output_flag = task.output_flag
    try:
        task.output_flag = None
        cmd_str, _ = task.build_command(target, **task_opts)
    finally:
        task.output_flag = saved_output_flag

    return cmd_str
