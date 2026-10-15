"""Declared tool module: ``dirsearch`` (web content discovery).

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


name = "dirsearch"
description = "Dirsearch web content discovery against a target URL."
args_schema: dict[str, Any] = {
    "target": {
        "type": "string",
        "description": "Target URL",
        "required": True,
    },
    "extensions": {
        "type": "string",
        "description": "Comma-separated extensions (-e)",
        "default": "php,html,js,json,txt,bak,zip",
    },
    "threads": {
        "type": "integer",
        "description": "Number of threads (-t)",
        "default": 30,
    },
    "output": {
        "type": "string",
        "description": "Report file name under output_dir/OFX_RUN_DIR",
        "default": "dirsearch_results.json",
    },
}


def run(ctx):
    if shutil.which("dirsearch") is None:
        raise RuntimeError("dirsearch is not installed (not on PATH)")
    target = _require_target(ctx)
    extensions = _text_arg(ctx, "extensions") or "php,html,js,json,txt,bak,zip"
    threads = _text_arg(ctx, "threads") or "30"
    output_name = _text_arg(ctx, "output") or "dirsearch_results.json"

    output = _run_dir(ctx) / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "dirsearch",
        "-u", target,
        "-e", extensions,
        "-t", str(threads),
        "--random-agent",
        "-O", "json",
        "-o", str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(
            f"dirsearch exited {proc.returncode}: {' | '.join(tail) or 'no output'}"
        )
    ctx.add_outputs(results_file=str(output))
    print(f"dirsearch report: {output}")
