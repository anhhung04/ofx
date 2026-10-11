"""Classify a target (domain/subdomain/cidr/ip) into per-type target files."""

from __future__ import annotations

import os

from ofx.api.recon.targets import split_targets


def run(ctx):
    src = str(ctx.inputs.get("target", ""))
    rd = os.environ["OFX_RUN_DIR"]
    values = open(src).read().splitlines() if os.path.isfile(src) else [src]
    groups = split_targets(values)
    counts = {t: len(items) for t, items in groups.items() if items}
    for gtype, items in groups.items():
        with open(os.path.join(rd, f"targets_{gtype}.txt"), "w") as fh:
            fh.write("\n".join(items))
    if len(counts) == 1:
        target_type = next(iter(counts))
    elif counts:
        target_type = "mixed"
    else:
        target_type = "unknown"
    print(f"target_type: {target_type} {counts}")
    ctx.add_outputs(target_type=target_type)
