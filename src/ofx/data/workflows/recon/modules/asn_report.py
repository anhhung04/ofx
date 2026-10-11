"""Report the ASN/IP-range discovery artifacts.

The ASN path must not report an empty success: when mapcidr left no CIDR file
the caller would otherwise continue with a "" target range.
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
    cidr_file = os.path.join(rd, "cidr_ranges.txt")
    asn_file = os.path.join(rd, "asn_cidrs.txt")
    if not os.path.isfile(cidr_file):
        raise RuntimeError(
            f"ASN/IP range discovery produced no results ({cidr_file} is missing); "
            "asnmap/mapcidr failed"
        )
    with open(cidr_file) as fh:
        cidrs = [line.strip() for line in fh if line.strip()]
    print(f"discovered {len(cidrs)} CIDR ranges")
    ctx.add_outputs(
        cidr_file=cidr_file,
        cidr_count=len(cidrs),
        asn_file=asn_file if os.path.isfile(asn_file) else "",
    )
