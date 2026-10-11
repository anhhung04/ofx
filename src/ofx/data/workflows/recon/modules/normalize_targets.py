"""Normalize a domain/file target into a per-line host list for dnsx."""

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
    src = str(ctx.inputs.get("target") or "").strip()
    rd = _artifact_dir(ctx)
    if os.path.isfile(src):
        with open(src) as fh:
            values = fh.read().splitlines()
    elif src:
        values = [src]
    else:
        raise RuntimeError("dns-enum needs a domain or a file of subdomains")
    targets = [value.strip() for value in values if value.strip()]
    if not targets:
        raise RuntimeError(f"dns-enum target {src!r} contains no hosts to resolve")
    out = os.path.join(rd, "dns_input.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(targets) + "\n")
    print(f"resolving {len(targets)} targets")
    ctx.add_outputs(input_file=out, target_count=len(targets))
