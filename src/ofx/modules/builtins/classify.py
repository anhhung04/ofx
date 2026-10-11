"""Builtin ``classify_targets`` module: split targets into typed lists.

Classifies a target input (file, literal, or ``source_type`` override) into
``domain``/``subdomain``/``cidr``/``ip``/``url``/``unknown`` groups using
:func:`ofx.api.recon.targets.split_targets`, writing one ``targets_<type>.txt``
per group under the run directory.

A target that is not an existing file and still looks like a path (``./list``,
``targets.txt``) is rejected as a typo instead of being classified — except
when it is itself a valid target (a CIDR such as ``10.0.0.0/24`` or a URL).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ofx.api.recon.targets import classify_target, split_targets
from ofx.modules.base import ModuleContext, ModuleResult
from ofx.modules.builtins._common import run_dir, text_arg

name = "classify_targets"
description = "Classify targets (domain/subdomain/cidr/ip/url) into typed files."
args_schema: dict[str, Any] = {
    "target": {
        "type": "string",
        "description": "Single target or path to a file with mixed targets",
        "required": True,
    },
    "source_type": {
        "type": "string",
        "enum": ["auto", "file", "target"],
        "description": "Input kind: auto (detect), file (must exist), or target (literal)",
    },
}

SOURCE_TYPES = ("auto", "file", "target")
"""Accepted ``source_type`` values."""

_FILE_SUFFIXES = (".txt", ".csv", ".lst", ".list", ".json", ".jsonl")
_PATH_MARKERS = ("/", "\\", "~")


def _has_path_marker(value: str) -> bool:
    """Return whether *value* carries a path marker (leading dot, ``/``, ``~``)."""
    return value.startswith(".") or any(marker in value for marker in _PATH_MARKERS)


def _has_file_suffix(value: str) -> bool:
    """Return whether *value* ends in a known artifact-file suffix."""
    return value.lower().endswith(_FILE_SUFFIXES)


def _is_literal_target(value: str) -> bool:
    """Return whether *value* classifies as a target on its own.

    CIDRs (``10.0.0.0/24``) and URLs (``https://example.com/x``) contain path
    markers but are targets, not file paths, so they must never trip the
    missing-file guard.
    """
    try:
        classify_target(value)
    except ValueError:
        return False
    return True


def _values(raw: str, source_type: str) -> list[str]:
    """Resolve the target input into the list of values to classify."""
    if source_type == "target":
        return [raw]

    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.read_text(errors="replace").splitlines()
    if source_type == "file":
        raise FileNotFoundError(f"target file not found: {candidate}")
    # A file suffix is a strong signal of a mistyped path, so it wins over
    # target validity (``example.json`` can be passed as ``source_type=target``);
    # bare path markers are only suspicious when the value is not a target.
    if _has_file_suffix(raw) or (_has_path_marker(raw) and not _is_literal_target(raw)):
        raise FileNotFoundError(
            f"target looks like a file path but does not exist: {candidate} "
            "(pass source_type=target to classify it as a literal target)"
        )
    return [raw]


def run(ctx: ModuleContext) -> ModuleResult:
    """Classify the target input and publish the per-type files and counts."""
    raw = text_arg(ctx, "target")
    if not raw:
        raise ValueError("target is required")

    source_type = text_arg(ctx, "source_type").lower() or "auto"
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"unsupported source_type {source_type!r}; supported values: "
            + ", ".join(SOURCE_TYPES)
        )

    out_dir = run_dir(ctx)

    groups = split_targets(_values(raw, source_type))
    target_files: dict[str, str] = {}
    counts: dict[str, int] = {}
    for target_kind, items in groups.items():
        path = str(out_dir / f"targets_{target_kind}.txt")
        with open(path, "w") as handle:
            handle.write("\n".join(items))
        target_files[target_kind] = path
        if items:
            counts[target_kind] = len(items)
            print(f"{target_kind}: {len(items)} -> {path}")

    if len(counts) == 1:
        target_type = next(iter(counts))
    elif counts:
        target_type = "mixed"
    else:
        target_type = "unknown"

    ctx.add_outputs(
        target_type=target_type,
        counts=json.dumps(counts, sort_keys=True),
        target_files=json.dumps(target_files, sort_keys=True),
    )
    print(f"target_type: {target_type}")
    return ModuleResult()


__all__ = ["args_schema", "description", "name", "run"]
