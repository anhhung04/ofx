"""Builtin ``python`` module: execute a Python script (inline or from a file)."""

from __future__ import annotations

import builtins
import os
import traceback
from contextlib import chdir, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleContext, ModuleResult

name = "python"
description = "Execute a Python script (inline `script` or `script_file` in `with:`)."
args_schema: dict[str, Any] = {
    "script": {"type": "string", "description": "Inline Python script code"},
    "script_file": {
        "type": "string",
        "description": "Path to a Python script file, resolved against the working directory",
    },
}


def run(ctx: ModuleContext) -> ModuleResult:
    """Execute the script synchronously (direct invocation entry point)."""
    script = str(ctx.args.get("script", ""))
    script_file = ctx.args.get("script_file")
    if not script and script_file:
        path = Path(script_file)
        if not path.is_absolute():
            path = ctx.working_directory / path
        try:
            script = path.read_text(encoding="utf-8")
        except OSError as exc:
            return ModuleResult(
                exit_code=1,
                stderr=f"Failed to read script file {path}: {exc}",
            )
    if not script:
        return ModuleResult(
            exit_code=1,
            stderr="python module requires 'script' or 'script_file' in args",
        )

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    globals_dict: dict[str, Any] = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "os": os,
        "__inputs__": ctx.inputs,
        "__secrets__": ctx.secrets,
        "__ctx__": ctx,
        "add_outputs": ctx.add_outputs or (lambda **_kwargs: None),
        "publish": ctx.publish,
        "subscribe": ctx.subscribe,
        "wait_for": ctx.wait_for,
    }
    try:
        with (
            chdir(ctx.working_directory),
            redirect_stdout(stdout_capture),
            redirect_stderr(stderr_capture),
        ):
            exec(script, globals_dict)
            exit_code = 0
    except Exception:
        stderr_capture.write(traceback.format_exc())
        exit_code = 1

    return ModuleResult(
        exit_code=exit_code,
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
    )


__all__ = ["args_schema", "description", "name", "run"]
