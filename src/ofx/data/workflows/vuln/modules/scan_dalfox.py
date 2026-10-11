"""Run dalfox against the target URL and record its JSONL report."""

from __future__ import annotations

import pathlib
import subprocess


def _target(ctx) -> str:
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")
    return target


def _run_dir(ctx) -> pathlib.Path:
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write scan results")
    return pathlib.Path(run_dir)


def run(ctx):
    target = _target(ctx)
    output = _run_dir(ctx) / "dalfox_results.jsonl"
    cmd = [
        "dalfox",
        "url",
        target,
        "--silence",
        "--format",
        "jsonl",
        "-o",
        str(output),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    ctx.add_outputs(results_file=str(output))
    print(f"dalfox report: {output}")
