"""Declared tool module: ``sqlmap`` (SQL injection scanner).

Self-contained: remote execution streams this file into a UDF wrapper, so it
must not import ``ofx.*``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot write scan results"


def _text_arg(ctx, key):
    """Return an argument as a stripped string (``""`` when unset)."""
    value = ctx.args.get(key, ctx.inputs.get(key))
    return "" if value is None else str(value).strip()


def _run_dir(ctx):
    """Return the artifact directory (``OFX_RUN_DIR``)."""
    candidate = (
        str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    ).strip()
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()


def _require_target(ctx):
    """Return the target input or raise."""
    target = _text_arg(ctx, "target")
    if not target:
        raise ValueError("target is required")
    return target


name = "sqlmap"
description = "sqlmap SQL injection scanner against a target URL."
args_schema: dict[str, Any] = {
    "target": {
        "type": "string",
        "description": "Target URL",
        "required": True,
    },
    "level": {
        "type": "integer",
        "description": "Test level (--level, 1-5)",
        "default": 2,
    },
    "risk": {
        "type": "integer",
        "description": "Risk level (--risk, 1-3)",
        "default": 2,
    },
    "output": {
        "type": "string",
        "description": "Report directory name under output_dir/OFX_RUN_DIR",
        "default": "sqlmap",
    },
}


def run(ctx):
    if shutil.which("sqlmap") is None:
        raise RuntimeError("sqlmap is not installed (not on PATH)")
    target = _require_target(ctx)
    level = _text_arg(ctx, "level") or "2"
    risk = _text_arg(ctx, "risk") or "2"
    output_name = _text_arg(ctx, "output") or "sqlmap"

    output = _run_dir(ctx) / output_name
    output.mkdir(parents=True, exist_ok=True)
    cmd = [
        "sqlmap",
        "-u", target,
        "--batch",
        "--random-agent",
        "--level", str(level),
        "--risk", str(risk),
        "--output-dir", str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(
            f"sqlmap exited {proc.returncode}: {' | '.join(tail) or 'no output'}"
        )
    ctx.add_outputs(results_dir=str(output))
    print(f"sqlmap output: {output}")
