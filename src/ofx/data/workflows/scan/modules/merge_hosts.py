"""Merge fping and naabu live-host lists into one de-duplicated file."""

from __future__ import annotations

import os


def run(ctx):
    rd = ctx.env.get("OFX_RUN_DIR", "")
    files = ["live_hosts.txt", "live_hosts_naabu.txt"]
    seen = set()
    for fn in files:
        fp = os.path.join(rd, fn)
        try:
            with open(fp) as f:
                for line in f:
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
        except FileNotFoundError:
            pass

    out = os.path.join(rd, "all_live_hosts.txt")
    with open(out, "w") as f:
        f.write("\n".join(sorted(seen)))
    print(f"Found {len(seen)} live hosts")
    ctx.add_outputs(host_count=len(seen), host_file=out)
