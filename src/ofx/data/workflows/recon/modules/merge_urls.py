"""Merge wayback, gau and katana URL outputs into a unique list.

Raises when none of the providers left an artifact: an empty URL list must mean
"no archived URLs", never "every provider failed".
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
    names = ("urls_wayback.txt", "urls_gau.txt", "urls_katana.txt")
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
            f"URL collection produced no results: none of "
            f"{', '.join(names)} were produced"
        )
    urls = sorted(seen)
    out = os.path.join(rd, "all_urls.txt")
    with open(out, "w") as fh:
        if urls:
            fh.write("\n".join(urls) + "\n")
    print(f"collected {len(urls)} unique URLs")
    ctx.add_outputs(url_file=out, url_count=len(urls))
