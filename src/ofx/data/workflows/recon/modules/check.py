"""Inspect AXFR results for a successful zone transfer."""

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
    results_file = os.path.join(rd, "axfr_results.txt")
    try:
        with open(results_file) as fh:
            content = fh.read()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"AXFR results are missing ({results_file}); the dig step produced "
            "no output"
        ) from exc
    if "XFR size" in content:
        print("ZONE TRANSFER SUCCEEDED — misconfiguration found")
        ctx.add_outputs(vulnerable="true", status="zone transfer succeeded")
    else:
        print("no zone transfer possible (expected)")
        ctx.add_outputs(vulnerable="false", status="no zone transfer")
