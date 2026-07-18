"""Shared task-step command helpers for cloud runner and sessions."""

from __future__ import annotations

from typing import Any

from ofx.models.step import Step
from ofx.runner.task_profile_options import (
    adapt_task_command_for_profile,
    merge_profile_task_options,
)
from ofx.runner.task_step import extract_task_target_and_opts

def build_task_command_from_step(
    step: Step,
    profile: Any | None = None,
) -> str:
    """Build a shell command for a ``task:`` workflow step.

    When *profile* is an :class:`~ofx.profiles.models.OFXProfile` instance,
    profile-level common settings (proxy, threads, rate_limit, delay,
    user_agent, jitter) and per-task ``task_options`` overrides are merged
    into the command — with step-level ``with:`` values always winning.
    """
    task_name = step.task
    if not task_name:
        raise RuntimeError("Task step is missing task name")

    from ofx.tasks.registry import TaskRegistry

    task_cls = TaskRegistry.get(task_name)
    if task_cls is None:
        raise RuntimeError(f"Task '{task_name}' is not registered")
    task = task_cls()

    target, task_opts = extract_task_target_and_opts(step.run_with)
    if profile is not None:
        task_opts, _injected, _override_keys = merge_profile_task_options(
            task_name=task_name,
            user_opts=task_opts,
            task_declared_opts=task.opts,
            profile=profile,
        )

    saved_output_flag = task.output_flag
    try:
        task.output_flag = None
        cmd_str, _ = task.build_command(target, **task_opts)
    finally:
        task.output_flag = saved_output_flag
    return adapt_task_command_for_profile(
        cmd_str,
        task_declared_opts=task.opts,
        resolved_opts=task_opts,
        profile=profile,
    )
