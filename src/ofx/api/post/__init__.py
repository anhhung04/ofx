"""Post-exploitation helper utilities."""

from __future__ import annotations

# Core abstractions
from .base import CommandRunner, PostRunnerBase

# Utilities
from .detect import detect_os
from .enum import linpeas_command, linux_exploit_suggester_command, winpeas_command
from .privilege import is_admin_from_whoami, is_root_from_id
from .registry import RunnerRegistry

# Runner implementations
from .runners import (
    PostSMBExec,
    PostSSH,
    PostWebShell,
    PostWinRM,
    PostWMIExec,
)
from .transfer import build_download_command

__all__ = [
    # Core
    "CommandRunner",
    "PostRunnerBase",
    "RunnerRegistry",
    # Runners
    "PostSSH",
    "PostWebShell",
    "PostWinRM",
    "PostSMBExec",
    "PostWMIExec",
    # Utilities
    "build_download_command",
    "detect_os",
    "is_admin_from_whoami",
    "is_root_from_id",
    "linpeas_command",
    "linux_exploit_suggester_command",
    "winpeas_command",
]
