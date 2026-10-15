"""Check Docker Compose availability and report its version."""

from __future__ import annotations

import subprocess


def _try(cmd: list[str]):
    try:
        return subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return None


def run(ctx):
    v2 = _try(["docker", "compose", "version", "--short"])
    if v2 is not None and v2.returncode == 0 and v2.stdout.strip():
        version = v2.stdout.strip()
        source = "docker compose"
    else:
        v1 = _try(["docker-compose", "--version"])
        if v1 is None or v1.returncode != 0:
            raise RuntimeError(
                "Docker Compose is not installed (neither 'docker compose' "
                "nor 'docker-compose' is available)"
            )
        version = v1.stdout.strip() or v1.stderr.strip()
        source = "docker-compose"

    ctx.add_outputs(compose_version=version)
    print(f"Docker Compose ({source}): {version}")
