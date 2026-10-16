"""Run trufflehog and report only redacted finding summaries.

trufflehog JSON output is written verbatim to a ``0600`` artifact; the step log
only lists the number of findings and the detector names, never secret values.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

_SUBCOMMANDS = {"git": "git", "filesystem": "filesystem"}


def run(ctx):
    source_path = str(ctx.inputs.get("source_path", "")).strip()
    if not source_path:
        raise ValueError("source_path is required (run resolve-source first)")

    scan_type = str(ctx.inputs.get("scan_type", "git")).strip().lower()
    subcommand = _SUBCOMMANDS.get(scan_type)
    if subcommand is None:
        raise ValueError(
            f"unsupported scan_type {scan_type!r} for trufflehog; "
            "supported values: git, filesystem"
        )

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the trufflehog report")

    results = pathlib.Path(run_dir) / "trufflehog_results.jsonl"
    cmd = [
        "trufflehog",
        subcommand,
        source_path,
        "--json",
        "--only-verified",
        "--no-update",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("trufflehog is not installed") from exc
    if proc.returncode not in (0, 183):
        raise RuntimeError(
            f"trufflehog failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )

    results.write_text(proc.stdout)
    results.chmod(0o600)

    findings = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            findings.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    detectors = sorted(
        {str(item.get("DetectorName", "unknown")) for item in findings if isinstance(item, dict)}
    )
    ctx.add_outputs(findings_count=str(len(findings)), results_file=str(results))
    print(f"trufflehog findings: {len(findings)}")
    if detectors:
        print("Detectors: " + ", ".join(detectors))
    print(f"Raw results: {results} (mode 0600)")
