"""Provision a DigitalOcean droplet via the doctl CLI (with dry-run support)."""

from __future__ import annotations

import json
import pathlib
import subprocess

_DEFAULT_DO_USER = "root"
_AWS_DEFAULT_SIZE = "t3.small"
_DO_DEFAULT_SIZE = "s-1vcpu-1gb"


def _run_json(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"failed to parse JSON output of '{' '.join(cmd[:4])}': {exc}"
        ) from exc


def _public_ipv4(droplet: dict) -> str:
    for entry in (droplet.get("networks") or {}).get("v4") or []:
        if entry.get("type") == "public":
            return str(entry.get("ip_address", ""))
    return ""


def run(ctx):
    name = str(ctx.inputs.get("instance_name", "")).strip() or "ofx-attack-infra"
    region = str(ctx.inputs.get("region", "")).strip() or "nyc3"
    image = str(ctx.inputs.get("image", "")).strip()
    size = str(ctx.inputs.get("size", "")).strip()
    key = str(ctx.inputs.get("ssh_key_name", "")).strip()
    user_data = str(ctx.inputs.get("user_data", "")).strip()
    dry_run = bool(ctx.inputs.get("dry_run", True))

    if not image or image.startswith("ami-"):
        raise RuntimeError(
            "DigitalOcean provisioning requires an image slug in --image "
            f"(e.g. ubuntu-22-04-x64); got {image!r}"
        )
    if not size or size == _AWS_DEFAULT_SIZE:
        size = _DO_DEFAULT_SIZE
    if user_data and not pathlib.Path(user_data).is_file():
        raise RuntimeError(f"cloud-init file not found: {user_data}")

    cmd = [
        "doctl",
        "compute",
        "droplet",
        "create",
        name,
        "--region",
        region,
        "--size",
        size,
        "--image",
        image,
        "--wait",
        "--output",
        "json",
    ]
    if key:
        cmd += ["--ssh-keys", key]
    if user_data:
        cmd += ["--user-data-file", user_data]

    if dry_run:
        print("[dry-run] " + " ".join(cmd))
        ctx.add_outputs(droplet_id="", public_ip="", ssh_command="")
        return

    droplets = _run_json(cmd)
    if not droplets:
        raise RuntimeError("doctl compute droplet create returned no droplet")
    droplet = droplets[0] if isinstance(droplets, list) else droplets
    droplet_id = str(droplet.get("id", "")).strip()
    public_ip = _public_ipv4(droplet)
    ssh_command = f"ssh {_DEFAULT_DO_USER}@{public_ip}" if public_ip else ""

    ctx.add_outputs(
        droplet_id=droplet_id,
        public_ip=public_ip,
        ssh_command=ssh_command,
    )
    print(f"Droplet ID: {droplet_id}")
    print(f"Public IP: {public_ip}")
    print(f"SSH: {ssh_command}")
