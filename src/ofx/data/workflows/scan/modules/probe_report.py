"""Summarize httpx output so later steps can gate on live web targets."""

from __future__ import annotations

import os


def _artifact_dir(ctx):
    """Return the directory holding this workflow's artifacts."""
    explicit = str(ctx.inputs.get("output_dir") or "").strip()
    run_dir = (
        explicit
        or os.environ.get("OFX_RUN_DIR")
        or str(ctx.env.get("OFX_RUN_DIR") or "")
    )
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate run artifacts")
    return run_dir


def run(ctx):
    rd = _artifact_dir(ctx)
    probe_file = os.path.join(rd, "httpx_results.txt")
    try:
        with open(probe_file) as fh:
            targets = [line.strip() for line in fh if line.strip()]
    except FileNotFoundError:
        targets = []
        print(f"httpx produced no results ({probe_file} is missing)")
    print(f"live web targets: {len(targets)}")
    ctx.add_outputs(probe_file=probe_file, live_url_count=len(targets))
