"""Auto-export typed findings to project directories.

Collects typed outputs (subdomains, URLs, ports, vulns, etc.) from all
job runners after workflow completion and writes them to organized
project subdirectories.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.runner.core import RunnerRegistryKeys
from ofx.settings import settings
from ofx.tasks.output_types import OUTPUT_TYPE_DIR_MAP, OUTPUT_TYPE_FILE_MAP

if TYPE_CHECKING:
    from ofx.runner.core import BaseRunner

logger = logging.getLogger(settings.app_branding)


def type_display_key(type_name: str, item: dict) -> str:
    """Extract the primary display value for a typed output item."""
    key_map: dict[str, Any] = {
        "ip": "ip",
        "port": lambda i: f"{i.get('ip', i.get('host', ''))}:{i.get('port', '')}",
        "subdomain": "host",
        "url": "url",
        "tag": "name",
        "record": lambda i: (
            f"{i.get('name', '')} {i.get('type', '')} {i.get('host', '')}"
        ),
        "domain": "domain",
    }
    extractor = key_map.get(type_name, "")
    if callable(extractor):
        return extractor(item).strip()
    if extractor:
        return str(item.get(extractor, "")).strip()
    return ""


def export_typed_outputs(
    project_path: str,
    all_typed_outputs: list,
    prefix: str = "",
) -> list[str]:
    """Export typed outputs to the correct project subdirectories.

    Args:
        project_path: Root project directory.
        all_typed_outputs: Flat list of typed output dicts.
        prefix: Optional filename prefix (e.g. workflow or job name).

    Returns:
        List of summary strings describing what was written.
    """
    if not project_path or not all_typed_outputs:
        return []

    p = Path(project_path)
    buckets: dict[str, list[dict]] = {}
    for item in all_typed_outputs:
        if not isinstance(item, dict):
            continue
        t = item.get("_type", "")
        if t:
            buckets.setdefault(t, []).append(item)

    summaries: list[str] = []
    for type_name, items in sorted(buckets.items()):
        subdir = OUTPUT_TYPE_DIR_MAP.get(type_name, "scans")
        filename = OUTPUT_TYPE_FILE_MAP.get(type_name, f"{type_name}.txt")
        if prefix:
            stem, ext = (filename.rsplit(".", 1) + [""])[:2]
            filename = f"{prefix}-{stem}.{ext}" if ext else f"{prefix}-{stem}"

        dest = p / subdir
        dest.mkdir(parents=True, exist_ok=True)
        fpath = dest / filename

        if filename.endswith(".jsonl"):
            safe_lines = []
            for i in items:
                try:
                    safe_lines.append(json.dumps(i, default=str))
                except (TypeError, ValueError):
                    continue
            existing = set()
            if fpath.exists():
                existing = set(fpath.read_text().strip().splitlines())
            new_lines = [ln for ln in safe_lines if ln not in existing]
            if new_lines:
                with open(fpath, "a") as f:
                    f.write("\n".join(new_lines) + "\n")
        else:
            values = set()
            for i in items:
                key = type_display_key(type_name, i)
                if key:
                    values.add(key)
            if fpath.exists():
                values.update(
                    ln for ln in fpath.read_text().strip().splitlines() if ln
                )
            if values:
                fpath.write_text("\n".join(sorted(values)) + "\n")

        summaries.append(f"  [+] {subdir}/{filename} ({len(items)} items)")

    return summaries


async def collect_typed_outputs(runners: dict[str, BaseRunner]) -> list[dict]:
    """Collect typed outputs from all job runners (including matrix children).

    Traverses the runner tree: WorkflowRunner → JobRunner/MatrixJobRunner →
    StepRunner, collecting typed_outputs from each step's registry outputs.
    """
    from ofx.runner.execution.job import JobRunner, MatrixJobRunner

    all_typed: list[dict] = []

    for _job_id, runner in runners.items():
        if isinstance(runner, MatrixJobRunner):
            # Matrix runner wraps multiple JobRunners
            for _child_id, child in runner._runners.items():
                if isinstance(child, JobRunner):
                    all_typed.extend(await _collect_from_job(child))
        elif isinstance(runner, JobRunner):
            all_typed.extend(await _collect_from_job(runner))
        else:
            # CloudJobRunner or other — try to get outputs directly
            try:
                outputs = await runner.reg_get(RunnerRegistryKeys.OUTPUTS)
                if outputs:
                    typed = outputs.get("typed_outputs", [])
                    if isinstance(typed, list):
                        all_typed.extend(typed)
            except Exception:
                pass

    return all_typed


async def _collect_from_job(job_runner: Any) -> list[dict]:
    """Collect typed outputs from all step runners within a job."""
    typed: list[dict] = []
    for _step_id, step_runner in job_runner._runners.items():
        try:
            outputs = await step_runner.reg_get(RunnerRegistryKeys.OUTPUTS)
            if outputs:
                step_typed = outputs.get("typed_outputs", [])
                if isinstance(step_typed, list):
                    typed.extend(step_typed)
        except Exception:
            continue
    return typed


async def auto_export_findings(
    runners: dict[str, Any],
    project_path: str | None,
    log_fn: Any = None,
) -> list[str]:
    """Collect and export all typed findings to the project directory.

    Called automatically after workflow completion when --project is set.

    Returns:
        List of summary lines describing exported files.
    """
    if not project_path:
        return []

    all_typed = await collect_typed_outputs(runners)
    if not all_typed:
        return []

    summaries = export_typed_outputs(project_path, all_typed)

    if summaries and log_fn:
        log_fn("Findings exported to project:")
        for s in summaries:
            log_fn(s)

    return summaries
