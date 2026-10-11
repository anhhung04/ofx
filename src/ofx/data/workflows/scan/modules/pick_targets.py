"""Select fuzz targets, skipping WAF/CDN-protected hosts."""

from __future__ import annotations

import os
import shutil


def run(ctx):
    rd = ctx.env.get("OFX_RUN_DIR", "")
    clean = str(ctx.inputs.get("clean_targets", ""))
    force = str(ctx.inputs.get("force", "false")).lower() == "true"
    src = str(ctx.inputs.get("target", ""))
    out = os.path.join(rd, "fuzz_targets.txt")
    if force or not clean or not os.path.isfile(clean):
        if os.path.isfile(src):
            shutil.copy(src, out)
        else:
            open(out, "w").write(src.strip() + "\n")
        if not force and not clean:
            print("no WAF/CDN filter available — fuzzing all targets")
    else:
        shutil.copy(clean, out)
        skipped = open(src).read().splitlines() if os.path.isfile(src) else [src]
        skipped = [s for s in skipped if s.strip() and s not in open(out).read()]
        for s in skipped:
            print(f"skipped (WAF/CDN): {s}")
    count = len([line for line in open(out).read().splitlines() if line.strip()])
    print(f"fuzz list: {count} targets")
    ctx.add_outputs(fuzz_targets=out)
