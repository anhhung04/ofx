"""Run a baseline gitleaks secret scan and write the JSON report.

gitleaks exit codes: ``0`` = no leaks, ``1`` = leaks found, anything else is an
operational failure (bad config, unreadable source, ...).
"""

from __future__ import annotations

import json
import pathlib
import subprocess


def run(ctx):
    repo_root = pathlib.Path(str(ctx.inputs.get("repo_root", "")).strip() or ".")
    if not repo_root.is_dir():
        raise RuntimeError(f"repository root not found: {repo_root}")

    baseline_file = repo_root / ".gitleaks-baseline.json"
    print("[*] Running baseline gitleaks scan...")
    try:
        proc = subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                str(repo_root),
                "--report-format",
                "json",
                "--report-path",
                str(baseline_file),
                "--verbose",
            ],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gitleaks is not installed") from exc

    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"gitleaks baseline scan failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )
    if proc.stdout.strip():
        print(proc.stdout.strip())

    findings_count = 0
    if baseline_file.is_file():
        baseline_file.chmod(0o600)
        try:
            report = json.loads(baseline_file.read_text() or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"baseline report {baseline_file} is not valid JSON: {exc}"
            ) from exc
        if isinstance(report, list):
            findings_count = len(report)
    elif proc.returncode == 1:
        raise RuntimeError("gitleaks reported leaks but wrote no baseline report")

    ctx.add_outputs(
        findings_count=str(findings_count),
        baseline_file=str(baseline_file),
    )
    print(f"Baseline findings: {findings_count}")
    print(f"Baseline report: {baseline_file}")
