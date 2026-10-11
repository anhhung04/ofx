"""Merge puredns and dnsx brute-force results into a unique list.

Partial results are kept, but when neither producer left an artifact the brute
force step never really ran and the empty list must not be mistaken for
"no subdomains exist".
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
    names = ("brute_puredns.txt", "brute_dnsx.txt")
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
            f"subdomain brute force produced no results: none of "
            f"{', '.join(names)} were produced"
        )
    subdomains = sorted(seen)
    out = os.path.join(rd, "brute_subdomains.txt")
    with open(out, "w") as fh:
        if subdomains:
            fh.write("\n".join(subdomains) + "\n")
    print(f"found {len(subdomains)} subdomains via brute force")
    ctx.add_outputs(subdomain_file=out, subdomain_count=len(subdomains))
