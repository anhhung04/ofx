"""Declared tool module: ``ffuf`` (web fuzzer).

Self-contained: remote execution streams this file into a UDF wrapper, so it
must not import ``ofx.*``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

NO_RUN_DIR_MESSAGE = "OFX_RUN_DIR is not set; cannot write scan results"

_WORDLIST = "/usr/share/seclists/Discovery/Web-Content/common.txt"
_MATCH_CODES = "200,204,301,302,307,401,403,405"


def _text_arg(ctx, key):
    """Return an argument as a stripped string (``""`` when unset)."""
    value = ctx.args.get(key, ctx.inputs.get(key))
    return "" if value is None else str(value).strip()


def _run_dir(ctx):
    """Return the artifact directory (``OFX_RUN_DIR``)."""
    candidate = (
        str(ctx.env.get("OFX_RUN_DIR") or "")
        or os.environ.get("OFX_RUN_DIR", "")
    ).strip()
    if not candidate:
        raise RuntimeError(NO_RUN_DIR_MESSAGE)
    return Path(candidate).expanduser()


def _require_target(ctx):
    """Return the target input or raise."""
    target = _text_arg(ctx, "target")
    if not target:
        raise ValueError("target is required")
    return target


name = "ffuf"
description = "ffuf web content fuzzer against a target URL."
args_schema: dict[str, Any] = {
    "target": {
        "type": "string",
        "description": "Target URL (FUZZ keyword is appended to the path)",
        "required": True,
    },
    "wordlist": {
        "type": "string",
        "description": "Wordlist path (-w)",
        "default": _WORDLIST,
    },
    "match_codes": {
        "type": "string",
        "description": "Match HTTP status codes (-mc)",
        "default": _MATCH_CODES,
    },
    "threads": {
        "type": "integer",
        "description": "Number of threads (-t)",
        "default": 50,
    },
    "output": {
        "type": "string",
        "description": "Report file name under output_dir/OFX_RUN_DIR",
        "default": "ffuf_results.json",
    },
}


def run(ctx):
    if shutil.which("ffuf") is None:
        raise RuntimeError("ffuf is not installed (not on PATH)")
    target = _require_target(ctx).rstrip("/")
    wordlist = _text_arg(ctx, "wordlist") or _WORDLIST
    match_codes = _text_arg(ctx, "match_codes") or _MATCH_CODES
    threads = _text_arg(ctx, "threads") or "50"
    output_name = _text_arg(ctx, "output") or "ffuf_results.json"

    output = _run_dir(ctx) / output_name
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffuf",
        "-u", f"{target}/FUZZ",
        "-w", wordlist,
        "-mc", match_codes,
        "-t", str(threads),
        "-o", str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(
            f"ffuf exited {proc.returncode}: {' | '.join(tail) or 'no output'}"
        )
    ctx.add_outputs(results_file=str(output))
    print(f"ffuf report: {output}")
