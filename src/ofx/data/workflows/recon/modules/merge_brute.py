"""Merge puredns and dnsx brute-force results into a unique list."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    seen = set()
    for name in ("brute_puredns.txt", "brute_dnsx.txt"):
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            pass
    out = os.path.join(rd, "brute_subdomains.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"found {len(seen)} subdomains via brute force")
    ctx.add_outputs(subdomain_file=out, subdomain_count=len(seen))
