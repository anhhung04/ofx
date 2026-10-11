"""Merge amass and subfinder subdomain outputs into a unique list.

Raises when both collectors failed so the empty list is never mistaken for a
domain without subdomains; a single successful collector is enough to continue.
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
    names = ("subdomains_amass.txt", "subdomains_subfinder.txt")
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
            f"passive subdomain enumeration produced no results: none of "
            f"{', '.join(names)} were produced"
        )
    subdomains = sorted(seen)
    out = os.path.join(rd, "all_subdomains.txt")
    with open(out, "w") as fh:
        if subdomains:
            fh.write("\n".join(subdomains) + "\n")
    print(f"Found {len(subdomains)} unique subdomains")
    ctx.add_outputs(subdomain_count=len(subdomains), subdomain_file=out)
