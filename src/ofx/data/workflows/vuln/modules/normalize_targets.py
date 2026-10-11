"""Normalize the nuclei target input into a target file path."""

from __future__ import annotations

import pathlib
import re


def run(ctx):
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the target file")

    candidate = pathlib.Path(target).expanduser()
    if candidate.is_file():
        target_file = candidate.resolve()
    elif "/" in target and "://" not in target:
        raise FileNotFoundError(f"target file not found: {candidate}")
    else:
        items = [item.strip() for item in re.split(r"[,\n]", target) if item.strip()]
        if not items:
            raise ValueError("target did not contain any usable value")
        target_file = pathlib.Path(run_dir) / "nuclei_targets.txt"
        target_file.write_text("\n".join(items) + "\n")

    ctx.add_outputs(target_file=str(target_file))
    print(f"Targets: {target_file}")
