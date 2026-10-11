"""Summarize TLS scanner artifacts and fail when every scanner produced nothing."""

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
    files = ["tls_certs.jsonl", "sslscan_results.xml", "testssl_results.json"]
    produced = []
    for name in files:
        path = os.path.join(rd, name)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            produced.append(path)
    if not produced:
        raise RuntimeError(
            f"every TLS scanner failed: none of {', '.join(files)} produced results"
        )
    print(f"TLS artifacts: {len(produced)}/{len(files)} ({', '.join(produced)})")
    ctx.add_outputs(tls_files=",".join(produced), scanner_count=len(produced))
