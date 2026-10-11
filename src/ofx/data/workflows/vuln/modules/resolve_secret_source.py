"""Resolve the secret-scan target into a scannable source path."""

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

    scan_type = str(ctx.inputs.get("scan_type", "git")).strip().lower()
    run_dir = str(ctx.env.get("OFX_RUN_DIR", "")).strip()
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot resolve the scan source")

    if scan_type == "url":
        raise ValueError(
            "scan_type 'url' is not supported (no HTTP URL secret scanner is "
            "configured); use 'git' for a repository URL or 'filesystem' for a "
            "local path"
        )

    if scan_type == "git":
        source_path = pathlib.Path(run_dir) / "secret-source"
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
    elif scan_type == "filesystem":
        if _URL_RE.match(target):
            raise ValueError(
                f"scan_type 'filesystem' expects a local path, got URL: {target}"
            )
        candidate = pathlib.Path(target).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(f"scan source not found: {candidate}")
        source_path = candidate.resolve()
    else:
        raise ValueError(
            f"unsupported scan_type {scan_type!r}; supported values: git, filesystem"
        )

    ctx.add_outputs(source_path=str(source_path), scan_type=scan_type)
    print(f"Scan source ({scan_type}): {source_path}")
