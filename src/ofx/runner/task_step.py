"""Shared helpers for task-based workflow steps."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

def extract_task_target_and_opts(
    run_with: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    """Return normalized task target text plus remaining task options.

    Accepts either ``target`` or ``targets`` from workflow step ``with:``
    values. Lists are normalized to the comma-separated form expected by the
    local task runner and cloud task command builder.
    """

    task_opts = dict(run_with)
    raw_target = task_opts.pop("target", task_opts.pop("targets", ""))
    if isinstance(raw_target, list):
        target = ",".join(str(item) for item in raw_target)
    else:
        target = str(raw_target)
    return target, task_opts

def extract_output_item_target(item: Mapping[str, Any]) -> str:
    """Return the best target label from a typed-output item."""
    for key in ("domain", "host", "ip"):
        value = item.get(key, "")
        if value:
            return str(value)

    url = item.get("url", "")
    if url:
        try:
            return urlparse(str(url)).hostname or ""
        except Exception:
            return ""
    return ""

__all__ = [
    "extract_output_item_target",
    "extract_task_target_and_opts",
]
