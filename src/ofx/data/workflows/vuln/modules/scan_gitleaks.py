"""Run gitleaks over a source path and report only redacted summaries.

Findings are written to a ``0600`` JSON report; the step output only lists the
rule, file, and line of each finding so secret values never reach the log.
gitleaks runs with ``--exit-code 0``, so any non-zero (or non-``1``) return code
is treated as an operational failure.
"""

from __future__ import annotations

import json
import pathlib
import subprocess


def _is_git_repo(path: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", path, "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return proc.returncode == 0


def _load_findings(report: pathlib.Path) -> list[dict]:
    if not report.is_file():
        return []
    try:
        data = json.loads(report.read_text() or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gitleaks report {report} is not valid JSON: {exc}") from exc
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def run(ctx):
    source_path = str(ctx.inputs.get("source_path", "")).strip()
    if not source_path:
        raise ValueError("source_path is required (run the resolve step first)")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the gitleaks report")

    report_name = (
        str(ctx.inputs.get("report_name", "")).strip() or "gitleaks_results.json"
    )
    report = pathlib.Path(run_dir) / report_name

    no_git = bool(ctx.inputs.get("no_git", False)) or not _is_git_repo(source_path)
    cmd = [
        "gitleaks",
        "detect",
        "--source",
        source_path,
        "--report-format",
        "json",
        "--report-path",
        str(report),
        "--redact",
        "--exit-code",
        "0",
    ]
    if no_git:
        cmd.append("--no-git")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("gitleaks is not installed") from exc
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"gitleaks failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )

    findings = _load_findings(report)
    if report.is_file():
        report.chmod(0o600)

    ctx.add_outputs(findings_count=str(len(findings)), results_file=str(report))
    print(f"gitleaks findings: {len(findings)}")
    for item in findings[:20]:
        rule = item.get("RuleID") or item.get("Description") or "rule"
        print(f"  {rule} {item.get('File', '')}:{item.get('StartLine', '')}")
    print(f"Report: {report} (mode 0600)")
