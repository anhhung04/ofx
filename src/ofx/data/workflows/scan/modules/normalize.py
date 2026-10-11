"""Normalize the target input into a per-line file for cdncheck/wafw00f."""

from __future__ import annotations

import os


def run(ctx):
    src = str(ctx.inputs.get("target", ""))
    rd = ctx.env.get("OFX_RUN_DIR", "")
    values = open(src).read().splitlines() if os.path.isfile(src) else [src]
    targets = [v.strip() for v in values if v.strip()]
    out = os.path.join(rd, "waf_input.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(targets))
    print(f"checking {len(targets)} targets")
