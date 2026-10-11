"""Builtin ``normalize_targets`` module: turn any target input into a file.

Accepts a target file, a single literal, or a comma/newline separated list of
literals and publishes a per-line target file plus the normalized count.

A target that already is a file is published in place (its absolute path) so
callers keep using the file they passed; literals are written under the run
directory. An empty input is an error: an empty target list must never reach
downstream tooling as if the producers had found nothing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot locate run artifacts"


def _arg(ctx, key):
    """Return a module argument from ``ctx.args`` (falling back to ``ctx.inputs``)."""
    if key in ctx.args:
        return ctx.args[key]
    return ctx.inputs.get(key)


def _text_arg(ctx, key):
    """Return a module argument as a stripped string (``""`` when unset)."""
    value = _arg(ctx, key)
    return "" if value is None else str(value).strip()


def _run_dir(ctx, override=""):
    """Return the artifact directory: explicit override, then ``OFX_RUN_DIR``."""
    candidate = (
        override
        or str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    )
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()



name = "normalize_targets"
description = (
    "Normalize a target (file, literal, or comma list) into a per-line target file."
)
args_schema: dict[str, Any] = {
    "target": {
        "type": "string",
        "description": "File path, literal target, or comma/newline separated literals",
        "required": True,
    },
    "output": {
        "type": "string",
        "description": "Output file name for literal targets (default targets_normalized.txt)",
    },
    "output_dir": {
        "type": "string",
        "description": "Directory holding the output file (default OFX_RUN_DIR)",
    },
}

DEFAULT_OUTPUT = "targets_normalized.txt"

_SPLIT_RE = re.compile(r"[,\n]")


def _split_literals(raw: str) -> list[str]:
    return [item.strip() for item in _SPLIT_RE.split(raw) if item.strip()]


def _count_lines(path: Path) -> int:
    with open(path) as handle:
        return sum(1 for line in handle if line.strip())


def run(ctx):
    """Publish a per-line target file for the configured target input."""
    raw = _text_arg(ctx, "target")
    if not raw:
        raise ValueError("normalize_targets requires a 'target' (file or literal)")

    candidate = Path(raw).expanduser()
    if candidate.is_file():
        target_file = candidate.resolve()
        try:
            count = _count_lines(target_file)
        except OSError as exc:
            raise RuntimeError(
                f"failed to read target file {target_file}: {exc}"
            ) from exc
        if count == 0:
            raise RuntimeError(f"target file {target_file} contains no targets")
        print(f"target file: {target_file} ({count} targets)")
        ctx.add_outputs(target_file=str(target_file), count=count)
        return None

    targets = _split_literals(raw)
    if not targets:
        raise ValueError("target did not contain any usable value")

    raw_output = _text_arg(ctx, "output") or DEFAULT_OUTPUT
    out_path = Path(raw_output).expanduser()
    if not out_path.is_absolute():
        out_dir = _run_dir(ctx, _text_arg(ctx, "output_dir"))
        out_path = out_dir / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(targets) + "\n")

    print(f"normalized {len(targets)} target(s) -> {out_path}")
    ctx.add_outputs(target_file=str(out_path), count=len(targets))
    return None


__all__ = ["args_schema", "description", "name", "run"]
