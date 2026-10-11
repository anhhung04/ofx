"""Classify targets into typed lists and write per-type files to the run dir."""
import json
import os

from ofx.api.recon.targets import split_targets


def run(ctx):
    src = str(ctx.inputs.get("target", ""))
    rd = ctx.env.get("OFX_RUN_DIR")
    values = open(src).read().splitlines() if os.path.isfile(src) else [src]

    groups = split_targets(values)
    counts = {}
    for gtype, items in groups.items():
        path = os.path.join(rd, f"targets_{gtype}.txt")
        with open(path, "w") as fh:
            fh.write("\n".join(items))
        if items:
            counts[gtype] = len(items)
            print(f"{gtype}: {len(items)} -> {path}")

    if len(counts) == 1:
        target_type = next(iter(counts))
    elif counts:
        target_type = "mixed"
    else:
        target_type = "unknown"
    print(f"target_type: {target_type}")
    ctx.add_outputs(target_type=target_type, counts=json.dumps(counts))
