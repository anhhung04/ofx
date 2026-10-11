"""Print the Tor SOCKS endpoint and a ready-to-run connectivity test."""

from __future__ import annotations


def run(ctx):
    socks = str(ctx.inputs.get("tor_socks", "")).strip()
    if not socks:
        raise RuntimeError("tor_socks was not published by the check-tor step")

    host, _, port = socks.partition(":")
    print(f"TOR endpoint: {host}:{port}")
    print(
        f"Test with: curl --socks5-hostname {host}:{port} "
        "https://check.torproject.org/api/ip"
    )
