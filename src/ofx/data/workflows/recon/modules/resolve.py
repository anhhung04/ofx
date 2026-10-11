"""Merge alterx and dnsgen permutation outputs into a unique list."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    seen = set()
    for name in ("permutations.txt", "permutations_dnsgen.txt"):
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            pass
    out = os.path.join(rd, "all_permutations.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"generated {len(seen)} permutations to resolve")
    ctx.add_outputs(subdomain_file=out, subdomain_count=len(seen))
