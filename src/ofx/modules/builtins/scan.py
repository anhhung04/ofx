"""Builtin ``scan_tool`` module: run one scanner binary, record its report.

Replaces the per-tool wrapper modules (``scan_dalfox``, ``scan_dirsearch``,
``scan_ffuf``, ``scan_sqlmap``, ``scan_tplmap``) with a single flag-driven
implementation: build the argv from ``args``, append the target and output
flags, run the binary, and publish the report file.

The command only runs when the binary exists — ``require_binary`` keeps the
failure explicit (no half-written report mistaken for a finding).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot write scan results"


def _arg(ctx, key):
    """Return a module argument from ``ctx.args`` (falling back to ``ctx.inputs``)."""
    if key in ctx.args:
        return ctx.args[key]
    return ctx.inputs.get(key)


def _text_arg(ctx, key):
    """Return a module argument as a stripped string (``""`` when unset)."""
    value = _arg(ctx, key)
    return "" if value is None else str(value).strip()


def _run_dir(ctx) -> Path:
    run_dir = (
        str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    ).strip()
    if not run_dir:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(run_dir).expanduser()


def _format_arg(spec: Any, target: str, output: Path) -> list[str]:
    """Expand one argv element; ``{target}``/``{output}`` placeholders substitute."""
    if isinstance(spec, list):
        rendered = [str(part) for part in spec]
    else:
        rendered = [str(spec)]
    return [
        part.replace("{target}", target).replace("{output}", str(output))
        for part in rendered
    ]


name = "scan_tool"
description = (
    "Run a scanner binary against a target and publish the report file. "
    "Pairs with capture_stdout for tools that write only to stdout."
)
args_schema: dict[str, Any] = {
    "tool": {
        "type": "string",
        "description": "Binary name (must exist on PATH)",
        "required": True,
    },
    "target": {
        "type": "string",
        "description": "Target URL/host; substitutes {target} in args",
        "required": True,
    },
    "args": {
        "type": "array",
        "items": {},
        "description": (
            "argv elements (an element may be a [flag, value] pair); "
            "{target} and {output} placeholders are expanded"
        ),
        "required": True,
    },
    "output": {
        "type": "string",
        "description": "Report file name under output_dir/OFX_RUN_DIR",
        "required": True,
    },
    "output_arg": {
        "type": "string",
        "description": "Flag that takes the output path (e.g. '-o'); omit when the tool only writes to stdout",
    },
    "capture_stdout": {
        "type": "boolean",
        "description": "Write the tool's stdout to the output file instead of passing output_arg",
        "default": False,
    },
    "extra_env": {
        "type": "object",
        "description": "Extra environment variables for the tool process",
    },
    "results_output_key": {
        "type": "string",
        "description": "Published output key for the report path",
        "default": "results_file",
    },
}


def run(ctx):
    tool = _text_arg(ctx, "tool")
    if not tool:
        raise ValueError("tool is required")
    if shutil.which(tool) is None:
        raise RuntimeError(f"{tool} is not installed (not on PATH)")

    target = _text_arg(ctx, "target")
    if not target:
        raise ValueError("target is required")

    output = _run_dir(ctx) / _text_arg(ctx, "output")
    output.parent.mkdir(parents=True, exist_ok=True)

    raw_args = _arg(ctx, "args") or []
    cmd: list[str] = [tool]
    for spec in raw_args:
        cmd.extend(_format_arg(spec, target, output))

    capture_stdout = bool(_arg(ctx, "capture_stdout"))
    output_arg = _text_arg(ctx, "output_arg")
    if not capture_stdout:
        if not output_arg:
            raise ValueError("output_arg or capture_stdout: true is required")
        cmd.extend([output_arg, str(output)])

    extra_env = _arg(ctx, "extra_env") or {}
    env = {**os.environ, **{str(k): str(v) for k, v in extra_env.items()}}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(
            f"{tool} exited {proc.returncode}: {' | '.join(tail) or 'no output'}"
        )
    if capture_stdout:
        output.write_text(proc.stdout)

    key = _text_arg(ctx, "results_output_key") or "results_file"
    ctx.add_outputs(**{key: str(output)})
    print(f"{tool} report: {output}")
