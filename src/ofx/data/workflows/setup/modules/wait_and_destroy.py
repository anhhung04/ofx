"""Wait for the teardown delay, then destroy the lab compose stack."""

from __future__ import annotations

import subprocess
import time


def _docker(args: list[str]) -> str:
    proc = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def run(ctx):
    compose_path = str(ctx.inputs.get("compose_path", "")).strip()
    if not compose_path:
        raise ValueError("compose_path is required to destroy the lab")
    lab_name = str(ctx.inputs.get("lab_name", "")).strip() or "ofx-lab"
    delay = int(str(ctx.inputs.get("teardown_delay", "0")).strip() or "0")

    if delay > 0:
        print(f"[*] Waiting {delay}s before teardown...")
        time.sleep(delay)

    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            lab_name,
            "-f",
            compose_path,
            "down",
            "-v",
            "--remove-orphans",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    remaining = _docker(
        ["ps", "-q", "--filter", f"label=com.docker.compose.project={lab_name}"]
    ).split()
    if remaining:
        raise RuntimeError(
            f"lab '{lab_name}' still has {len(remaining)} container(s) after teardown"
        )

    ctx.add_outputs(destroyed="true")
    print(f"[+] Lab '{lab_name}' destroyed")
