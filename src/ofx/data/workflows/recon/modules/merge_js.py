"""Merge subjs and katana JS file outputs into a unique list.

A missing katana artifact is tolerated, but a missing subjs artifact means the
primary collector never ran and must not be reported as "no JavaScript found".
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
    required = "js_files_subjs.txt"
    optional = "js_files_katana.txt"
    seen = set()
    try:
        with open(os.path.join(rd, required)) as fh:
            seen.update(line.strip() for line in fh if line.strip())
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"subjs produced no results ({required} is missing); "
            "cannot collect JavaScript files"
        ) from exc
    try:
        with open(os.path.join(rd, optional)) as fh:
            seen.update(line.strip() for line in fh if line.strip())
    except FileNotFoundError:
        print(f"katana produced no results ({optional} is missing)")

    files = sorted(seen)
    out = os.path.join(rd, "js_files.txt")
    with open(out, "w") as fh:
        if files:
            fh.write("\n".join(files) + "\n")
    print(f"collected {len(files)} JS files")
    ctx.add_outputs(js_file=out, js_count=len(files))
