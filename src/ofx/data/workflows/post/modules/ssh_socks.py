"""Generate SSH SOCKS/port-forward tunnel commands for manual launch.

Requires an explicit ``pivot_host`` and ``pivot_user`` — the previous version
fell back to the attacker's own ``lhost`` as the SSH destination, which would
have pointed the tunnel at the operator's host. Commands are written to a
run-scoped file; nothing is launched.
"""

import os


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the pivot commands")
    return run_dir


def run(ctx):
    pivot_host = str(ctx.inputs.get("pivot_host") or "").strip()
    pivot_user = str(ctx.inputs.get("pivot_user") or "").strip()
    if not pivot_host:
        raise ValueError(
            "'pivot_host' is required for ssh tunneling "
            "(it is never defaulted to the attacker host)"
        )
    if not pivot_user:
        raise ValueError("'pivot_user' is required for ssh tunneling")

    socks_port = str(ctx.inputs.get("socks_port") or "").strip()
    if not socks_port:
        raise ValueError("'socks_port' is required")

    target_host = str(ctx.inputs.get("target_host") or "").strip()
    target_port = str(ctx.inputs.get("target_port") or "").strip()

    lines = [
        "# SSH pivoting — MANUAL LAUNCH REQUIRED",
        f"# pivot: {pivot_user}@{pivot_host}",
        "",
        f"# Dynamic SOCKS proxy (then: proxychains / socks5 127.0.0.1 {socks_port})",
        f"ssh -D {socks_port} -N -f {pivot_user}@{pivot_host}",
        "",
        "# Dynamic SOCKS proxy bound to loopback only (stricter)",
        f"ssh -D 127.0.0.1:{socks_port} -N -f {pivot_user}@{pivot_host}",
    ]

    if target_host and target_port:
        lines += [
            "",
            f"# Remote port forward: {target_host}:{target_port} reachable via pivot",
            f"ssh -R {target_port}:{target_host}:{target_port} -N -f {pivot_user}@{pivot_host}",
            "",
            f"# Local port forward to {target_host}:{target_port}",
            f"ssh -L {target_port}:{target_host}:{target_port} -N -f {pivot_user}@{pivot_host}",
        ]

    run_dir = _run_dir(ctx)
    out = os.path.join(run_dir, "ssh_pivot_commands.txt")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    for line in lines:
        print(line)
    print(f"[+] Commands written to {out}")

    ctx.add_outputs(
        method="ssh",
        command_file=out,
        socks_port=socks_port,
        pivot_host=pivot_host,
        pivot_user=pivot_user,
        target_host=target_host,
        target_port=target_port,
    )
