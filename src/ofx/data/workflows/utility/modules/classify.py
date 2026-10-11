"""Classify targets into typed lists and write per-type files to the run dir."""

from __future__ import annotations

import json
import os
import pathlib

from ofx.api.recon.targets import split_targets

_SOURCE_TYPES = ("auto", "file", "target")
_FILE_SUFFIXES = (".txt", ".csv", ".lst", ".list", ".json", ".jsonl")
_PATH_MARKERS = ("/", "\\", "~")


def _looks_like_path(value: str) -> bool:
    return (
        value.startswith(".")
        or any(marker in value for marker in _PATH_MARKERS)
        or value.lower().endswith(_FILE_SUFFIXES)
    )


def run(ctx):
    raw = str(ctx.inputs.get("target", "")).strip()
    if not raw:
        raise ValueError("target is required")

    source_type = str(ctx.inputs.get("source_type", "auto")).strip().lower() or "auto"
    if source_type not in _SOURCE_TYPES:
        raise ValueError(
            f"unsupported source_type {source_type!r}; supported values: "
            + ", ".join(_SOURCE_TYPES)
        )

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the target files")

    if source_type == "target":
        values = [raw]
    else:
        candidate = pathlib.Path(raw).expanduser()
        if candidate.is_file():
            values = candidate.read_text(errors="replace").splitlines()
        elif source_type == "file":
            raise FileNotFoundError(f"target file not found: {candidate}")
        elif _looks_like_path(raw):
            raise FileNotFoundError(
                f"target looks like a file path but does not exist: {candidate} "
                "(pass source_type=target to classify it as a literal target)"
            )
        else:
            values = [raw]

    groups = split_targets(values)
    target_files: dict[str, str] = {}
    counts: dict[str, int] = {}
    for gtype, items in groups.items():
        path = os.path.join(run_dir, f"targets_{gtype}.txt")
        with open(path, "w") as handle:
            handle.write("\n".join(items))
        target_files[gtype] = path
        if items:
            counts[gtype] = len(items)
            print(f"{gtype}: {len(items)} -> {path}")

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
