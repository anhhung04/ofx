"""Run ffuf content discovery and record its JSON report."""

from __future__ import annotations

import pathlib
import subprocess

_WORDLIST = "/usr/share/seclists/Discovery/Web-Content/common.txt"
_MATCH_CODES = "200,204,301,302,307,401,403,405"


def _target(ctx) -> str:
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")
    return target


def _run_dir(ctx) -> pathlib.Path:
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write scan results")
    return pathlib.Path(run_dir)


def run(ctx):
    target = _target(ctx).rstrip("/")
    output = _run_dir(ctx) / "ffuf_results.json"
    cmd = [
        "ffuf",
        "-u",
        f"{target}/FUZZ",
        "-w",
        _WORDLIST,
        "-mc",
        _MATCH_CODES,
        "-t",
        "50",
        "-o",
        str(output),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    ctx.add_outputs(results_file=str(output))
    print(f"ffuf report: {output}")
