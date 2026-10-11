"""Launch the Docker Compose lab and count its running containers."""

from __future__ import annotations

import subprocess


def _docker(args: list[str]) -> str:
    proc = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def run(ctx):
    compose_path = str(ctx.inputs.get("compose_path", "")).strip()
    if not compose_path:
        raise ValueError("compose_path is required to launch the lab")
    lab_name = str(ctx.inputs.get("lab_name", "")).strip() or "ofx-lab"

    print(f"[*] Starting lab '{lab_name}'...")
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            lab_name,
            "-f",
            compose_path,
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "120",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())

    names = _docker(
        [
            "ps",
            "--filter",
            f"label=com.docker.compose.project={lab_name}",
            "--format",
            "{{.Names}}",
        ]
    ).split()

    ctx.add_outputs(containers=str(len(names)))
    print(f"Running containers: {len(names)}")
