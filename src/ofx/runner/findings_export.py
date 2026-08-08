"""Auto-export typed findings to project directories.

Collects typed outputs (subdomains, URLs, ports, vulns, etc.) from all
job runners after workflow completion and writes them to organized
project subdirectories — grouped by target when ``_target`` metadata
is present on the items.

Directory layout::

    <project>/
        subdomains/
            subdomains.txt          ← master (all targets merged)
            example.com/
                subdomains.txt      ← per-target
            other.net/
                subdomains.txt
        hosts/
            ports.txt               ← master
            10.10.10.5/
                ports.txt           ← per-target
        web/
            urls.txt                ← master
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.runner_refs import runner_leaf_descendants
from ofx.runner.target_paths import sanitize_target_slug
from ofx.settings import settings

_OUTPUT_TYPE_DIR_MAP: dict[str, str] = {
    "ip": "hosts",
    "port": "hosts",
    "subdomain": "subdomains",
    "url": "web",
    "vulnerability": "vulns",
    "tag": "web",
    "record": "subdomains",
    "domain": "osint",
    "certificate": "certs",
    "exploit": "vulns",
    "user_account": "evidence/creds",
}

_OUTPUT_TYPE_FILE_MAP: dict[str, str] = {
    "ip": "ips.txt",
    "port": "ports.txt",
    "subdomain": "subdomains.txt",
    "url": "urls.txt",
    "vulnerability": "vulnerabilities.jsonl",
    "tag": "tags.txt",
    "record": "dns-records.txt",
    "domain": "domains.txt",
    "certificate": "certificates.jsonl",
    "exploit": "exploits.jsonl",
    "user_account": "accounts.jsonl",
}

if TYPE_CHECKING:
    from ofx.runner.runner import Runner

logger = logging.getLogger(settings.app_branding)

_TEXT_EXPORT_KEY_EXTRACTORS: dict[str, Any] = {
    "ip": "ip",
    "port": lambda item: (
        f"{item.get('ip', item.get('host', ''))}:{item.get('port', '')}"
    ),
    "subdomain": "host",
    "url": "url",
    "tag": "name",
    "record": lambda item: (
        f"{item.get('name', '')} {item.get('type', '')} {item.get('host', '')}"
    ),
    "domain": "domain",
}

def export_typed_outputs(
    project_path: str,
    all_typed_outputs: list,
    prefix: str = "",
) -> list[str]:
    """Export typed outputs to the correct project subdirectories.

    Items that carry a ``_target`` field are additionally written into
    a per-target subdirectory (e.g. ``subdomains/example.com/subdomains.txt``).
    Master files (all targets merged) are always written for compatibility.

    Args:
        project_path: Root project directory.
        all_typed_outputs: Flat list of typed output dicts.
        prefix: Optional filename prefix (e.g. workflow or job name).

    Returns:
        List of summary strings describing what was written.
    """
    if not project_path or not all_typed_outputs:
        return []

    project_root = Path(project_path)
    items_by_export_path: dict[tuple[str, str], list[dict]] = {}

    for item in all_typed_outputs:
        if not isinstance(item, dict):
            continue

        type_name = item.get("_type", "")
        if not type_name:
            continue

        items_by_export_path.setdefault((type_name, ""), []).append(item)

        target_slug = sanitize_target_slug(item.get("_target", ""))
        if target_slug:
            items_by_export_path.setdefault((type_name, target_slug), []).append(item)

    summaries: list[str] = []
    for (type_name, target_slug), items in sorted(items_by_export_path.items()):
        subdir = _OUTPUT_TYPE_DIR_MAP.get(type_name, "scans")
        filename = _OUTPUT_TYPE_FILE_MAP.get(type_name, f"{type_name}.txt")
        if prefix:
            filename_path = Path(filename)
            filename = f"{prefix}-{filename_path.stem}{filename_path.suffix}"

        relative_dir = Path(subdir)
        if target_slug:
            relative_dir /= target_slug
        summary_path = (relative_dir / filename).as_posix()

        dest = project_root / relative_dir
        dest.mkdir(parents=True, exist_ok=True)
        fpath = dest / filename
        is_jsonl = fpath.suffix == ".jsonl"
        existing_lines = set(fpath.read_text().splitlines()) if fpath.exists() else set()

        if is_jsonl:
            candidate_lines: list[str] = []
            for item in items:
                try:
                    candidate_lines.append(json.dumps(item, default=str))
                except (TypeError, ValueError):
                    continue
        else:
            existing_lines = {line for line in existing_lines if line}
            extractor = _TEXT_EXPORT_KEY_EXTRACTORS.get(type_name)
            candidate_keys: set[str] = set()
            for item in items:
                if callable(extractor):
                    extracted_key = extractor(item)
                elif extractor:
                    extracted_key = str(item.get(extractor, ""))
                else:
                    extracted_key = ""

                stripped_key = extracted_key.strip()
                if stripped_key:
                    candidate_keys.add(stripped_key)
            candidate_lines = sorted(candidate_keys)

        new_lines = [line for line in candidate_lines if line not in existing_lines]
        if new_lines:
            if is_jsonl:
                with open(fpath, "a") as file_obj:
                    file_obj.write("\n".join(new_lines) + "\n")
            else:
                merged = set(existing_lines) | set(new_lines)
                fpath.write_text("\n".join(sorted(merged)) + "\n")
        elif not is_jsonl and existing_lines:
            fpath.write_text("\n".join(sorted(existing_lines)) + "\n")

        new_count = len(new_lines)
        label = f"{len(items)} items"
        if new_count < len(items):
            label += f", {new_count} new"
        summaries.append(f"  [+] {summary_path} ({label})")

    return summaries

async def collect_typed_outputs(runners: dict[str, Runner]) -> list[dict]:
    """Collect typed outputs from all job runners (including matrix children).

    Traverses the runner tree down to leaf runners and collects each leaf
    runner's ``typed_outputs`` payload when present.
    """
    leaf_runners = [
        typed_runner
        for runner in runners.values()
        for typed_runner in runner_leaf_descendants(runner)
    ]
    if not leaf_runners:
        return []

    results = await asyncio.gather(
        *(typed_runner.reg_get(RunnerRegistryKeys.OUTPUTS) for typed_runner in leaf_runners),
        return_exceptions=True,
    )

    all_typed: list[dict] = []
    for typed_runner, outputs in zip(leaf_runners, results, strict=True):
        if isinstance(outputs, Exception):
            model = getattr(typed_runner, "model", None)
            runner_label = (
                getattr(model, "jid", None)
                or getattr(model, "name", None)
                or "<unknown>"
            )
            logger.debug(
                "Failed to collect typed outputs from %s: %s",
                runner_label,
                outputs,
            )
            continue
        typed_outputs = outputs.get("typed_outputs") if isinstance(outputs, dict) else None
        if isinstance(typed_outputs, list):
            all_typed.extend(typed_outputs)
    return all_typed
