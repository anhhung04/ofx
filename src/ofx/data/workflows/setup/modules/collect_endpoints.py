"""Collect lab container endpoints from docker ps JSON output."""

from __future__ import annotations

import json
import subprocess


def run(ctx):
    project = str(ctx.inputs.get("project_label", "")).strip()
    if not project:
        raise ValueError("project_label is required to select lab containers")

    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--format",
            "{{json .}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    endpoints = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = data.get("Names", "")
        ports = data.get("Ports", "")
        status = data.get("Status", "unknown")
        endpoints.append(f"{name}: {ports} [{status}]")

    ctx.add_outputs(
        endpoints="\n".join(endpoints),
        containers=str(len(endpoints)),
    )
    for endpoint in endpoints:
        print(f"  {endpoint}")
