"""Summarize nuclei JSONL results by severity."""

from __future__ import annotations

import json
import os


def run(ctx):
    f = os.path.join(ctx.env.get("OFX_RUN_DIR", ""), "nuclei_results.jsonl")
    severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    try:
        with open(f) as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                    sev = item.get("info", {}).get("severity", "info").lower()
                    severity_count[sev] = severity_count.get(sev, 0) + 1
                except Exception:
                    pass
        total = sum(severity_count.values())
        print(f"Total findings: {total}")
        for k, v in severity_count.items():
            if v:
                print(f"  {k}: {v}")
    except FileNotFoundError:
        print("No nuclei results found")
