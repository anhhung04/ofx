"""Reject web-scan scan types that this workflow does not implement."""

from __future__ import annotations

SUPPORTED_SCAN_TYPES = ("sqli", "xss", "ssti", "all")


def run(ctx):
    scan_type = str(ctx.inputs.get("scan_type", "all")).strip().lower()
    if scan_type not in SUPPORTED_SCAN_TYPES:
        raise ValueError(
            f"unsupported scan_type {scan_type!r}; supported values: "
            + ", ".join(SUPPORTED_SCAN_TYPES)
            + " (ssrf and cmdi scanning are not implemented)"
        )
    ctx.add_outputs(scan_type=scan_type)
    print(f"Scan type: {scan_type}")
