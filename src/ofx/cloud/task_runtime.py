"""Shared task-step command helpers for cloud runner and sessions."""

from __future__ import annotations

from typing import Any

from ofx.models.step import Step


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
    from ofx.tasks.registry import TaskRegistry

    if not step.task:
        raise RuntimeError("Task step is missing task name")

    task_cls = TaskRegistry.get(step.task)
    if task_cls is None:
        raise RuntimeError(f"Task '{step.task}' is not registered")

    task = task_cls()

    task_opts = dict(step.run_with)
    target = str(task_opts.pop("target", task_opts.pop("targets", "")))

    # Apply profile settings (profile values yield to explicit step opts)
    if profile is not None:
        task_opts = _merge_profile_opts(task, step.task, task_opts, profile)

    saved_output_flag = task.output_flag
    try:
        task.output_flag = None
        cmd_str, _ = task.build_command(target, **task_opts)
    finally:
        task.output_flag = saved_output_flag

    return cmd_str


_COMMON_MAPPING: list[tuple[str, list[str]]] = [
    ("proxy", ["proxy", "proxy_url", "http_proxy"]),
    ("threads", ["threads", "concurrency", "workers"]),
    ("rate_limit", ["rate_limit", "rate"]),
    ("delay", ["delay"]),
    ("user_agent", ["user_agent"]),
    ("jitter", ["jitter"]),
]


def _merge_profile_opts(
    task: Any,
    task_name: str,
    user_opts: dict[str, Any],
    profile: Any,
) -> dict[str, Any]:
    """Merge profile auto-mapped & per-task opts, user opts always win."""
    merged = dict(user_opts)
    task_declared = task.opts  # declared opts for this tool

    # Layer 1: auto-map common profile fields
    for profile_attr, candidate_names in _COMMON_MAPPING:
        value = getattr(profile, profile_attr, None)
        if value is None:
            continue
        if isinstance(value, (int, float)) and value == 0:
            continue
        if isinstance(value, str) and not value:
            continue
        for opt_name in candidate_names:
            if opt_name in task_declared and opt_name not in merged:
                merged[opt_name] = value
                break

    # Layer 2: per-task overrides
    task_options = getattr(profile, "task_options", None) or {}
    overrides = task_options.get(task_name, {})
    if overrides:
        base = dict(overrides)
        base.update(merged)  # user opts win
        merged = base

    return merged
