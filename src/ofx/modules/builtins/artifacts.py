"""Builtin ``require_artifacts`` module: fail when producers wrote nothing.

Replaces the per-workflow "fail when every scanner produced nothing" report
modules (``osint_report``, ``tls_report``). An empty result must never be
mistaken for "the scan found nothing of interest", so the step fails hard
unless at least ``min_count`` of the expected files exist and are non-empty.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot locate run artifacts"


def _arg(ctx, key):
    """Return a module argument from ``ctx.args`` (falling back to ``ctx.inputs``)."""
    if key in ctx.args:
        return ctx.args[key]
    return ctx.inputs.get(key)


def _run_dir(ctx) -> Path:
    explicit = _arg(ctx, "output_dir")
    candidate = (
        str(explicit).strip()
        if explicit
        else (str(ctx.env.get("OFX_RUN_DIR") or "") or os.environ.get("OFX_RUN_DIR", ""))
    )
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()


name = "require_artifacts"
description = (
    "Fail when fewer than min_count of the expected artifact files exist and "
    "are non-empty; publishes produced_files and produced_count."
)
args_schema: dict[str, Any] = {
    "files": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Artifact file names (relative to output_dir/OFX_RUN_DIR)",
        "required": True,
    },
    "output_dir": {
        "type": "string",
        "description": "Artifact directory override (default OFX_RUN_DIR)",
    },
    "min_count": {
        "type": "integer",
        "description": "Minimum number of produced artifacts required (default 1)",
        "default": 1,
    },
    "label": {
        "type": "string",
        "description": "What produced these artifacts (used in messages)",
        "default": "producers",
    },
}


def run(ctx):
    rd = _run_dir(ctx)
    files = _arg(ctx, "files") or []
    if isinstance(files, str):
        files = [f.strip() for f in files.split(",") if f.strip()]
    if not files:
        raise ValueError("files is required")
    min_count = int(_arg(ctx, "min_count") or 1)
    label = str(_arg(ctx, "label") or "producers")

    produced = []
    for name_ in files:
        path = rd / name_
        if path.is_file() and path.stat().st_size > 0:
            produced.append(str(path))
    if len(produced) < min_count:
        raise RuntimeError(
            f"every {label} failed: fewer than {min_count} of "
            f"{', '.join(files)} produced results"
        )
    print(f"{label} artifacts: {len(produced)}/{len(files)} ({', '.join(produced)})")
    ctx.add_outputs(
        produced_files=",".join(produced),
        produced_count=len(produced),
    )
