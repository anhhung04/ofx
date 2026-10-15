"""Shared project-path resolution used by both runner and CLI layers.

Keeps ``ofx.runner`` from importing ``ofx.commands.project``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def get_active_project_path() -> Path | None:
    """Return the active project root, or ``None``."""
    try:
        from ofx.profiles import get_active_project

        return get_active_project()
    except Exception:
        return None


def get_project_run_dir(workflow_name: str) -> Path | None:
    """Return ``<project>/runs/<YYYY-MM-DD>_<workflow>/``, creating it.

    Returns ``None`` when no project is active.
    """
    active = get_active_project_path()
    if active is None:
        return None
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    run_dir = active / "runs" / f"{date_str}_{workflow_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def get_project_workflow_dir() -> Path | None:
    """Return ``<project>/workflows/``, creating it."""
    active = get_active_project_path()
    if active is None:
        return None
    workflows_dir = active / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    return workflows_dir
