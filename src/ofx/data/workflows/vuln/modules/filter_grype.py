"""Filter the grype JSON report down to the requested severities."""

from __future__ import annotations

import json
import pathlib


def run(ctx):
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate the grype report")

    source = pathlib.Path(run_dir) / "grype_results.json"
    if not source.is_file():
        raise RuntimeError(f"grype results not found: {source}")

    severities = {
        item.strip().upper()
        for item in str(ctx.inputs.get("severity", "")).split(",")
        if item.strip()
    }
    try:
        report = json.loads(source.read_text() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"grype report {source} is not valid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise RuntimeError(f"grype report {source} has an unexpected structure")

    matches = [item for item in report.get("matches", []) if isinstance(item, dict)]
    filtered = [
        item
        for item in matches
        if not severities
        or str((item.get("vulnerability") or {}).get("severity", "")).upper()
        in severities
    ]

    report["matches"] = filtered
    output = pathlib.Path(run_dir) / "grype_results_filtered.json"
    output.write_text(json.dumps(report, indent=2))

    ctx.add_outputs(report_path=str(output), findings_count=str(len(filtered)))
    print(f"grype findings: {len(filtered)} of {len(matches)} match the severity filter")
    print(f"Filtered report: {output}")
