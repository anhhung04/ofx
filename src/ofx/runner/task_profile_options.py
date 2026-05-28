"""Shared profile option merging helpers for task execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

COMMON_TASK_PROFILE_MAPPING: list[tuple[str, list[str]]] = [
    ("proxy", ["proxy", "proxy_url", "http_proxy"]),
    ("threads", ["threads", "concurrency", "workers"]),
    ("rate_limit", ["rate_limit", "rate"]),
    ("delay", ["delay"]),
    ("user_agent", ["user_agent"]),
    ("jitter", ["jitter"]),
]


def merge_profile_task_options(
    *,
    task_name: str,
    user_opts: Mapping[str, Any],
    task_declared_opts: Mapping[str, Any] | None,
    profile: Any,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Merge common profile settings and per-task overrides.

    Returns `(merged_opts, injected_common_opts, override_keys)`.
    User-provided options always win over profile-provided values.
    """

    merged = dict(user_opts)
    declared = task_declared_opts or {}
    injected: list[str] = []

    for profile_attr, candidate_names in COMMON_TASK_PROFILE_MAPPING:
        value = getattr(profile, profile_attr, None)
        if value is None:
            continue
        if isinstance(value, (int, float)) and value == 0:
            continue
        if isinstance(value, str) and not value:
            continue

        for opt_name in candidate_names:
            if opt_name in declared and opt_name not in merged:
                merged[opt_name] = value
                injected.append(f"{opt_name}={value}")
                break

    task_options = getattr(profile, "task_options", None) or {}
    overrides = task_options.get(task_name, {})
    override_keys = list(overrides.keys()) if overrides else []
    if overrides:
        base = dict(overrides)
        base.update(merged)
        merged = base

    return merged, injected, override_keys


__all__ = ["COMMON_TASK_PROFILE_MAPPING", "merge_profile_task_options"]
