"""Run sqlmap against the target URL and record its output directory."""

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
    output_dir = _run_dir(ctx) / "sqlmap"
    cmd = [
        "sqlmap",
        "-u",
        target,
        "--batch",
        "--random-agent",
        "--level",
        "2",
        "--risk",
        "2",
        "--output-dir",
        str(output_dir),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    ctx.add_outputs(results_dir=str(output_dir))
    print(f"sqlmap output: {output_dir}")
