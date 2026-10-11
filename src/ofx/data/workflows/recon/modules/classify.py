"""Classify a target (domain/subdomain/cidr/ip) into per-type target files."""

from __future__ import annotations

import os

from ofx.api.recon.targets import split_targets


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
    src = str(ctx.inputs.get("target") or "")
    rd = _artifact_dir(ctx)
    if os.path.isfile(src):
        with open(src) as fh:
            values = fh.read().splitlines()
    elif src.strip():
        values = [src]
    else:
        raise RuntimeError("classify needs a target (domain, IP, or CIDR)")
    groups = split_targets(values)
    counts = {t: len(items) for t, items in groups.items() if items}
    for gtype, items in groups.items():
        with open(os.path.join(rd, f"targets_{gtype}.txt"), "w") as fh:
            if items:
                fh.write("\n".join(items) + "\n")
    if len(counts) == 1:
        target_type = next(iter(counts))
    elif counts:
        target_type = "mixed"
    else:
        target_type = "unknown"
    print(f"target_type: {target_type} {counts}")
    ctx.add_outputs(target_type=target_type, target_count=sum(counts.values()))
