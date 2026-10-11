"""Merge passive and brute-force subdomain lists into a unique set.

Partial results are kept, but when neither producer supplied a readable list
the merge inputs were missing (a failed producer) and the empty result must not
be passed on as "no subdomains exist".
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
    sources = [
        str(ctx.inputs.get("passive_file") or ""),
        str(ctx.inputs.get("brute_file") or ""),
    ]
    seen = set()
    readable = []
    for src in sources:
        if not src:
            continue
        try:
            with open(src) as fh:
                seen.update(line.strip() for line in fh if line.strip())
            readable.append(src)
        except OSError:
            pass
    if not readable:
        raise RuntimeError(
            "no subdomain lists available to merge; the passive and brute-force "
            f"producers produced nothing (looked for {', '.join(s for s in sources if s)})"
        )
    subdomains = sorted(seen)
    out = os.path.join(rd, "all_subdomains.txt")
    with open(out, "w") as fh:
        if subdomains:
            fh.write("\n".join(subdomains) + "\n")
    print(f"total unique subdomains: {len(subdomains)}")
    ctx.add_outputs(subdomains=out, count=len(subdomains))
