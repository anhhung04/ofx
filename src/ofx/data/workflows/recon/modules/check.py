"""Inspect AXFR results for a successful zone transfer."""

from __future__ import annotations

import os


def run(ctx):
    rd = os.environ["OFX_RUN_DIR"]
    try:
        content = open(os.path.join(rd, "axfr_results.txt")).read()
    except FileNotFoundError:
        content = ""
    if "XFR size" in content:
        print("ZONE TRANSFER SUCCEEDED — misconfiguration found")
        ctx.add_outputs(vulnerable="true")
    else:
        print("no zone transfer possible (expected)")
        ctx.add_outputs(vulnerable="false")
