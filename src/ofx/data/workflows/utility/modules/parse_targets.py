"""Parse a target file into typed target lists."""

from __future__ import annotations

import json
import pathlib

from ofx.api.recon.targets import split_targets


def run(ctx):
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the target lists")

    source = pathlib.Path(target).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"target file not found: {source}")
    try:
        raw = source.read_text(errors="replace")
    except OSError as exc:
        raise RuntimeError(f"failed to read {source}: {exc}") from exc

    values = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    deduped = list(dict.fromkeys(values))

    groups = split_targets(deduped)
    target_files: dict[str, str] = {}
    counts: dict[str, int] = {}
    for gtype, items in groups.items():
        output = pathlib.Path(run_dir) / f"targets_{gtype}.txt"
        output.write_text("\n".join(items) + ("\n" if items else ""))
        target_files[gtype] = str(output)
        if items:
            counts[gtype] = len(items)
            print(f"{gtype}: {len(items)} -> {output}")

    ctx.add_outputs(
        target_files=json.dumps(target_files, sort_keys=True),
        counts=json.dumps(counts, sort_keys=True),
    )
    print(f"Parsed {len(deduped)} target(s) from {source}")
