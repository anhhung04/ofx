"""Merge amass and subfinder subdomain outputs into a unique list."""

from __future__ import annotations

import os


def run(ctx):
    files = [
        os.path.join(os.environ["OFX_RUN_DIR"], "subdomains_amass.txt"),
        os.path.join(os.environ["OFX_RUN_DIR"], "subdomains_subfinder.txt"),
    ]
    seen = set()
    all_subs = []
    for f in files:
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
                        all_subs.append(line)
        except FileNotFoundError:
            pass

    out = os.path.join(os.environ["OFX_RUN_DIR"], "all_subdomains.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(sorted(all_subs)))
    print(f"Found {len(all_subs)} unique subdomains")
    ctx.add_outputs(subdomain_count=len(all_subs), subdomain_file=out)
