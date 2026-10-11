"""Merge passive and brute-force subdomain lists into a unique set."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    sources = [
        ctx.inputs.get("passive_file", ""),
        ctx.inputs.get("brute_file", ""),
    ]
    seen = set()
    for src in sources:
        try:
            with open(src) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except (FileNotFoundError, OSError):
            pass
    out = os.path.join(rd, "all_subdomains.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"total unique subdomains: {len(seen)}")
    ctx.add_outputs(subdomains=out, count=len(seen))
