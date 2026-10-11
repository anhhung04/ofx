"""Builtin ``shell`` module: execute shell commands (legacy ``run:`` steps)."""

from __future__ import annotations

import os
import subprocess
import traceback
from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleContext, ModuleResult
from ofx.settings import DEFAULT_SHELL

name = "shell"
description = "Execute a shell command (equivalent to a legacy ``run:`` step)."
args_schema: dict[str, Any] = {
    "cmd": {
        "type": "string",
        "description": "Shell command to execute",
        "required": True,
    },
    "shell": {"type": "string", "description": "Shell to use"},
    "working_directory": {"type": "string", "description": "Working directory"},
    "timeout_minutes": {"type": "integer", "description": "Timeout in minutes"},
    "interactive": {
        "type": "boolean",
        "description": "Interactive stdin/stdout passthrough",
    },
}


def run(ctx: ModuleContext) -> ModuleResult:
    """Execute the command synchronously (direct invocation entry point)."""
    cmd = str(ctx.args.get("cmd", ""))
    if not cmd:
        return ModuleResult(exit_code=1, stderr="shell module requires 'cmd' in args")
    shell = str(ctx.args.get("shell", DEFAULT_SHELL))
    working_directory = Path(ctx.args.get("working_directory", ctx.working_directory))
    timeout_seconds = float(ctx.args.get("timeout_minutes", 1440)) * 60
    env = {**os.environ, **{str(key): str(value) for key, value in ctx.env.items()}}
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            executable=shell,
            cwd=working_directory,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ModuleResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except Exception:
        return ModuleResult(exit_code=1, stderr=traceback.format_exc())


__all__ = ["args_schema", "description", "name", "run"]
