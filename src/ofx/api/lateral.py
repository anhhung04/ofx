"""Convenience wrappers for lateral movement runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.api.post.registry import RunnerRegistry

__all__ = ["copy_and_exec", "exec_command"]


def copy_and_exec(
    target: str,
    src: str | Path,
    dst: str,
    *,
    method: str = "smbexec",
    command: str | None = None,
    **runner_kwargs: Any,
) -> str:
    """Upload a file then execute it via a registered post runner."""
    runner = RunnerRegistry.create(method, host=target, **runner_kwargs)
    runner.upload(str(Path(src).expanduser()), dst)
    return runner.run(command or dst)


def exec_command(
    target: str,
    command: str,
    *,
    method: str = "ssh",
    **runner_kwargs: Any,
) -> str:
    """Execute a single command via a registered post runner."""
    runner = RunnerRegistry.create(method, host=target, **runner_kwargs)
    return runner.run(command)
