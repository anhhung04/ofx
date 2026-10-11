"""Check whether Docker is installed and report its version."""

from __future__ import annotations

import subprocess


def run(ctx):
    try:
        proc = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker is not installed (docker not found in PATH)") from exc

    version = proc.stdout.strip() or proc.stderr.strip()
    ctx.add_outputs(docker_version=version)
    print(f"Docker: {version}")
