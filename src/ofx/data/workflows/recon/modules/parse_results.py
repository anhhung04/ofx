"""Parse dnsx output into a structured DNS record listing."""

from __future__ import annotations

import os

RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA")


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
    out = os.path.join(rd, "dns_records.txt")
    records = {}
    try:
        with open(out) as fh:
            lines = [line.strip() for line in fh if line.strip()]
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"dnsx produced no output ({out} is missing); DNS enumeration failed"
        ) from exc
    for line in lines:
        for token in line.split():
            record_type = token.strip("[]")
            if record_type in RECORD_TYPES:
                records[record_type] = records.get(record_type, 0) + 1
        print(line)
    if records:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(records.items()))
        print(f"Record counts: {summary}")
    ctx.add_outputs(
        dns_file=out,
        record_count=len(lines),
        record_types=",".join(sorted(records)),
    )
