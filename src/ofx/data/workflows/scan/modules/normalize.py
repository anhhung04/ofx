"""Normalize the target input into a per-line file for cdncheck/wafw00f."""

from __future__ import annotations

import os


def _artifact_dir(ctx):
    """Return the directory holding this workflow's artifacts.

    Reused workflows receive the caller's run directory as ``output_dir`` so
    the caller can keep reading the artifacts after this workflow finishes;
    standalone runs fall back to their own run directory.
    """
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
    src = str(ctx.inputs.get("target") or "").strip()
    rd = _artifact_dir(ctx)
    if os.path.isfile(src):
        with open(src) as fh:
            values = fh.read().splitlines()
    elif src:
        values = [src]
    else:
        raise RuntimeError("waf-detect needs a target host/URL or a file of targets")
    targets = [value.strip() for value in values if value.strip()]
    if not targets:
        raise RuntimeError(f"waf-detect target {src!r} contains no hosts to check")
    out = os.path.join(rd, "waf_input.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(targets) + "\n")
    print(f"checking {len(targets)} targets")
    ctx.add_outputs(input_file=out, normalized_count=len(targets))
