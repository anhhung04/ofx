"""Check container health statuses for the running lab."""

from __future__ import annotations

import subprocess


def _docker(args: list[str]) -> str:
    proc = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def run(ctx):
    project = str(ctx.inputs.get("project_label", "")).strip()
    if not project:
        raise ValueError("project_label is required to select lab containers")

    names = [
        name
        for name in _docker(
            [
                "ps",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--format",
                "{{.Names}}",
            ]
        ).splitlines()
        if name.strip()
    ]

    healthy = 0
    failed = 0
    for name in names:
        status = _docker(
            [
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}"
                "{{else}}{{.State.Status}}{{end}}",
                name,
            ]
        )
        if status in {"healthy", "running"}:
            healthy += 1
        else:
            failed += 1
        print(f"  {name}: {status}")

    ctx.add_outputs(healthy=str(healthy), failed=str(failed), containers=str(len(names)))
    print(f"Healthy: {healthy}, failed: {failed}")
