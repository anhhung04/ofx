"""Builtin ``python`` module: execute a Python script (inline or from a file).

This is the single code path for ``module: python`` steps: :class:`ModuleRunner`
invokes :func:`run` with a :class:`~ofx.modules.base.ModuleContext`, locally,
and the module must stay self-contained (stdlib plus :mod:`ofx.modules.base`)
so its source can be streamed for remote execution.

Behavior mirrors the removed ``ScriptRunner``/``exec_script_in_process``:
scripts get injected scope models (``__job__``/``__step__``/``__workflow__``),
a real channel store for ``publish``/``subscribe``/``wait_for`` (wired on the
context by the module runner), ``export_typed_outputs``, and ``add_outputs``
that both accumulates in-memory outputs and appends ``key=value`` lines to the
``$RUNNER_OUTPUTS`` file.  ``ctx.env`` variables are exported into
``os.environ`` for the duration of the script and restored afterwards.
"""

from __future__ import annotations

import builtins
import json
import os
import traceback
from contextlib import chdir, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from ofx.modules.base import (
    PYTHON_MODULE_REQUIRES_SCRIPT,
    ModuleContext,
    ModuleResult,
)

name = "python"
description = "Execute a Python script (inline `script` or `script_file` in `with:`)."
args_schema: dict[str, Any] = {
    "script": {"type": "string", "description": "Inline Python script code"},
    "script_file": {
        "type": "string",
        "description": "Path to a Python script file, resolved against the working directory",
    },
}


def write_outputs_file(outputs_file: str | os.PathLike[str] | None, **kwargs: Any) -> None:
    """Append ``key=value`` output lines, JSON-encoding structured values.

    Mirrors the removed ``ofx.modules.execution.command.write_outputs_file``:
    dicts/lists are JSON-serialized, everything else is stringified.
    """
    if not outputs_file:
        return

    with open(outputs_file, "a") as handle:
        for key, value in kwargs.items():
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            handle.write(f"{key}={serialized}\n")


def run(ctx: ModuleContext) -> ModuleResult:
    """Execute the script synchronously (single code path for python steps)."""
    script = str(ctx.args.get("script", ""))
    script_file = ctx.args.get("script_file")
    if not script and script_file:
        path = Path(script_file)
        if not path.is_absolute():
            # Relative script files resolve against the workflow directory (the
            # legacy ModuleRunner behavior), falling back to the working dir.
            workflow_dir = ctx.workflow_dir or ctx.working_directory
            candidates = [
                workflow_dir / path,
                ctx.working_directory / path,
            ]
            path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
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
            stderr=PYTHON_MODULE_REQUIRES_SCRIPT,
        )

    scope_models = ctx.scope_models or (None, None, None)
    workflow_model, job_model, step_model = scope_models
    outputs_file = ctx.env.get("RUNNER_OUTPUTS") or ctx.env.get("OFX_OUTPUTS")

    outputs: dict[str, Any] = {}

    def _add_outputs(**kwargs: Any) -> None:
        outputs.update(kwargs)
        if ctx.add_outputs is not None:
            ctx.add_outputs(**kwargs)
        write_outputs_file(outputs_file, **kwargs)

    def _parse_outputs_file() -> dict[str, str]:
        """Read ``key=value`` lines from the outputs file (no delete).

        The step runner owns cleanup of the file; the builtin only reads it.
        Mirrors the legacy ScriptRunner merge: file values (strings) win over
        the in-memory dict so downstream ``steps.<name>.outputs`` templates
        resolve to JSON-serialized strings (matching the old behavior).
        """
        if not outputs_file or not Path(outputs_file).exists():
            return {}
        parsed: dict[str, str] = {}
        for line in Path(outputs_file).read_text().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key_name, value = line.split("=", 1)
            key_name = key_name.strip()
            value = value.strip()
            if key_name:
                parsed[key_name] = value
        return parsed

    # Imported lazily: ofx.runner is never bundled for remote execution, so the
    # module-level imports stay limited to ofx.modules.base.
    from ofx.runner.findings_export import export_typed_outputs

    stdout_capture = StringIO()
    stderr_capture = StringIO()
    globals_dict: dict[str, Any] = {
        "__builtins__": builtins.__dict__,
        "__name__": "__main__",
        "os": os,
        "__job__": job_model,
        "__step__": step_model,
        "__workflow__": workflow_model,
        "__inputs__": ctx.inputs,
        "__ctx__": ctx,
        "__secrets__": ctx.secrets,
        "add_outputs": _add_outputs,
        "publish": ctx.publish,
        "subscribe": ctx.subscribe,
        "wait_for": ctx.wait_for,
        "export_typed_outputs": export_typed_outputs,
    }

    previous_env = {str(key): os.environ.get(str(key)) for key in ctx.env}
    os.environ.update({str(key): str(value) for key, value in ctx.env.items()})
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
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    outputs.update(_parse_outputs_file())

    return ModuleResult(
        exit_code=exit_code,
        stdout=stdout_capture.getvalue(),
        stderr=stderr_capture.getvalue(),
        outputs=outputs,
    )


__all__ = ["args_schema", "description", "name", "run", "write_outputs_file"]
