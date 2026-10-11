"""Merge alterx and dnsgen permutation outputs into a unique list.

A missing list from one generator is tolerated, but when neither generator
produced an artifact the permutation step failed and must not be reported as
"zero candidates".
"""

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
    names = ("permutations.txt", "permutations_dnsgen.txt")
    seen = set()
    missing = []
    for name in names:
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            missing.append(name)
    if len(missing) == len(names):
        raise RuntimeError(
            f"permutation generation produced no results: none of "
            f"{', '.join(names)} were produced"
        )
    permutations = sorted(seen)
    out = os.path.join(rd, "all_permutations.txt")
    with open(out, "w") as fh:
        if permutations:
            fh.write("\n".join(permutations) + "\n")
    print(f"generated {len(permutations)} permutations to resolve")
    ctx.add_outputs(subdomain_file=out, subdomain_count=len(permutations))
