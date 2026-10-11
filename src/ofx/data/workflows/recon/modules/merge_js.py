"""Merge subjs and katana JS file outputs into a unique list."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    seen = set()
    for name in ("js_files_subjs.txt", "js_files_katana.txt"):
        try:
            with open(os.path.join(rd, name)) as fh:
                seen.update(line.strip() for line in fh if line.strip())
        except FileNotFoundError:
            pass
    out = os.path.join(rd, "js_files.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(seen)))
    print(f"collected {len(seen)} JS files")
    ctx.add_outputs(js_file=out, js_count=len(seen))
