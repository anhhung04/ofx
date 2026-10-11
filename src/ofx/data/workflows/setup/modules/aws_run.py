"""Provision an AWS EC2 instance via the aws CLI (with dry-run support)."""

from __future__ import annotations

import json
import pathlib
import subprocess

_DEFAULT_AWS_USER = "ubuntu"


def _run_json(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"failed to parse JSON output of '{' '.join(cmd[:3])}': {exc}"
        ) from exc


def run(ctx):
    name = str(ctx.inputs.get("instance_name", "")).strip() or "ofx-attack-infra"
    region = str(ctx.inputs.get("region", "")).strip() or "us-east-1"
    image = str(ctx.inputs.get("image", "")).strip()
    size = str(ctx.inputs.get("size", "")).strip() or "t3.small"
    key = str(ctx.inputs.get("ssh_key_name", "")).strip()
    security_group = str(ctx.inputs.get("security_group", "")).strip()
    user_data = str(ctx.inputs.get("user_data", "")).strip()
    dry_run = bool(ctx.inputs.get("dry_run", True))

    if not image.startswith("ami-"):
        raise RuntimeError(
            "AWS provisioning requires an AMI ID in --image "
            f"(e.g. ami-0123456789abcdef0); got {image!r}"
        )
    if user_data and not pathlib.Path(user_data).is_file():
        raise RuntimeError(f"cloud-init file not found: {user_data}")

    cmd = [
        "aws",
        "ec2",
        "run-instances",
        "--region",
        region,
        "--image-id",
        image,
        "--instance-type",
        size,
        "--tag-specifications",
        f"ResourceType=instance,Tags=[{{Key=Name,Value={name}}}]",
        "--query",
        "Instances[0].InstanceId",
        "--output",
        "json",
    ]
    if key:
        cmd += ["--key-name", key]
    if security_group:
        cmd += ["--security-group-ids", security_group]
    if user_data:
        cmd += ["--user-data", f"file://{user_data}"]

    if dry_run:
        print("[dry-run] " + " ".join(cmd))
        ctx.add_outputs(instance_id="", public_ip="", ssh_command="")
        return

    instance_id = str(_run_json(cmd) or "").strip()
    if not instance_id:
        raise RuntimeError("aws ec2 run-instances returned no instance id")

    subprocess.run(
        [
            "aws",
            "ec2",
            "wait",
            "instance-running",
            "--region",
            region,
            "--instance-ids",
            instance_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    public_ip = str(
        _run_json(
            [
                "aws",
                "ec2",
                "describe-instances",
                "--region",
                region,
                "--instance-ids",
                instance_id,
                "--query",
                "Reservations[0].Instances[0].PublicIpAddress",
                "--output",
                "json",
            ]
        )
        or ""
    ).strip()
    ssh_command = f"ssh {_DEFAULT_AWS_USER}@{public_ip}" if public_ip else ""

    ctx.add_outputs(
        instance_id=instance_id,
        public_ip=public_ip,
        ssh_command=ssh_command,
    )
    print(f"Instance ID: {instance_id}")
    print(f"Public IP: {public_ip}")
    print(f"SSH: {ssh_command}")
