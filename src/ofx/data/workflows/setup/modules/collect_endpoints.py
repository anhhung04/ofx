"""Collect lab container endpoints from docker ps JSON output."""
import json
import subprocess


def run(ctx):
    lab_name = str(ctx.inputs.get("lab_name", "ofx-lab"))
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={lab_name}", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
    )

    endpoints = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            name = data.get("Names", "")
            ports = data.get("Ports", "")
            status = data.get("Status", "unknown")
            endpoints.append(f"{name}: {ports} [{status}]")
        except json.JSONDecodeError:
            continue

    ctx.add_outputs(endpoints="\n".join(endpoints))
    for ep in endpoints:
        print(f"  {ep}")
