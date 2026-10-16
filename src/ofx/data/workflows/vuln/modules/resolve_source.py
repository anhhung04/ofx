"""Resolve the code-scan target to a local source path (cloning repo URLs)."""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

_URL_RE = re.compile(r"^(?:https?|git|ssh)://|^git@[^:]+:")


def run(ctx):
    target = str(ctx.inputs.get("target", "")).strip()
    if not target:
        raise ValueError("target is required")

    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot clone the source")

    if _URL_RE.match(target):
        source_path = pathlib.Path(run_dir) / "source"
        if source_path.exists():
            shutil.rmtree(source_path)
        try:
            subprocess.run(
                ["git", "clone", "--quiet", target, str(source_path)],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "git is not installed; cannot clone the target repository"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"git clone failed for {target}: {exc.stderr.strip()}"
            ) from exc
    else:
        candidate = pathlib.Path(target).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(f"source path not found: {candidate}")
        source_path = candidate.resolve()

    ctx.add_outputs(source_path=str(source_path))
    print(f"Source: {source_path}")
