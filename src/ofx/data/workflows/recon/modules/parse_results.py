"""Parse dnsx output into a structured DNS record listing."""

from __future__ import annotations

import os


def run(ctx):
    records: dict[str, int] = {}
    out = os.path.join(os.environ["OFX_RUN_DIR"], "dns_records.txt")
    try:
        with open(out) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                for token in line.split():
                    if token.strip("[]") in ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA"):
                        rtype = token.strip("[]")
                        records[rtype] = records.get(rtype, 0) + 1
                print(line)
    except FileNotFoundError:
        print("No DNS records found")
    if records:
        print("Record counts: " + ", ".join(f"{k}={v}" for k, v in sorted(records.items())))
    ctx.add_outputs(dns_file=out)
