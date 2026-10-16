"""Summarize nuclei JSONL results by severity."""

from __future__ import annotations

import json
import pathlib


def run(ctx):
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot locate the nuclei results")

    results_file = pathlib.Path(run_dir) / "nuclei_results.jsonl"
    if not results_file.is_file():
        raise RuntimeError(
            f"nuclei results file not found: {results_file} "
            "(the nuclei scan did not produce any output)"
        )

    severity_count: dict[str, int] = {}
    total = 0
    for lineno, line in enumerate(results_file.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"corrupt nuclei result on line {lineno} of {results_file}: {exc}"
            ) from exc
        severity = str(item.get("info", {}).get("severity", "unknown")).lower()
        severity_count[severity] = severity_count.get(severity, 0) + 1
        total += 1

    ctx.add_outputs(
        total=str(total),
        severity_count=json.dumps(severity_count, sort_keys=True),
    )
    print(f"Total findings: {total}")
    for severity, count in sorted(severity_count.items()):
        print(f"  {severity}: {count}")
