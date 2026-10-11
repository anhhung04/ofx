"""Builtin ``normalize_targets`` module: turn any target input into a file.

Accepts a target file, a single literal, or a comma/newline separated list of
literals and publishes a per-line target file plus the normalized count.

A target that already is a file is published in place (its absolute path) so
callers keep using the file they passed; literals are written under the run
directory. An empty input is an error: an empty target list must never reach
downstream tooling as if the producers had found nothing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleContext, ModuleResult
from ofx.modules.builtins._common import run_dir, text_arg

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


def run(ctx: ModuleContext) -> ModuleResult:
    """Publish a per-line target file for the configured target input."""
    raw = text_arg(ctx, "target")
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
        return ModuleResult()

    targets = _split_literals(raw)
    if not targets:
        raise ValueError("target did not contain any usable value")

    out_dir = run_dir(ctx, text_arg(ctx, "output_dir"))
    out_path = out_dir / (text_arg(ctx, "output") or DEFAULT_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(targets) + "\n")

    print(f"normalized {len(targets)} target(s) -> {out_path}")
    ctx.add_outputs(target_file=str(out_path), count=len(targets))
    return ModuleResult()


__all__ = ["args_schema", "description", "name", "run"]
