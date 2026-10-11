"""Verify the Tor SOCKS endpoint is reachable and publish its address."""

from __future__ import annotations

import socket

_CONNECT_TIMEOUT_SECONDS = 5.0


def run(ctx):
    host = str(ctx.inputs.get("proxy_host", "127.0.0.1")).strip() or "127.0.0.1"
    port = str(ctx.inputs.get("proxy_port", "9050")).strip() or "9050"
    socks = f"{host}:{port}"
    ctx.add_outputs(tor_status="not-running", tor_socks=socks)

    try:
        with socket.create_connection((host, int(port)), timeout=_CONNECT_TIMEOUT_SECONDS):
            pass
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Tor SOCKS endpoint {socks} is not reachable: {exc}. "
            "Start Tor or point proxy_host/proxy_port at a running SOCKS proxy."
        ) from exc

    ctx.add_outputs(tor_status="running", tor_socks=socks)
    print(f"Tor SOCKS endpoint reachable: {socks}")
