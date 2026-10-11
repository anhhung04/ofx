"""Merge wayback, gau and katana URL outputs into a unique list."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    seen = set()
    for name in ("urls_wayback.txt", "urls_gau.txt", "urls_katana.txt"):
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            pass
    out = os.path.join(rd, "all_urls.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"collected {len(seen)} unique URLs")
    ctx.add_outputs(url_file=out, url_count=len(seen))
