"""Verify VPN connectivity and resolve the external IP when active."""

from __future__ import annotations

import subprocess

VPN_INTERFACES = ("tun0", "utun0", "ppp0", "wg0")
_EXTERNAL_IP_URL = "https://ifconfig.me"


def _interface_ipv4(iface: str) -> str:
    proc = subprocess.run(
        ["ip", "-4", "addr", "show", "dev", iface],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    for line in proc.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "inet":
            return fields[1].split("/")[0]
    return ""


def _external_ip() -> str:
    proc = subprocess.run(
        ["curl", "-s", "--max-time", "5", _EXTERNAL_IP_URL],
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def run(ctx):
    for iface in VPN_INTERFACES:
        link = subprocess.run(
            ["ip", "link", "show", "dev", iface],
            capture_output=True,
            text=True,
        )
        if link.returncode != 0:
            continue
        external_ip = _interface_ipv4(iface)
        ctx.add_outputs(vpn_active="true", external_ip=external_ip)
        print(f"[+] VPN interface active: {iface} ({external_ip or 'no IPv4'})")
        return

    external_ip = _external_ip()
    ctx.add_outputs(vpn_active="false", external_ip=external_ip)
    raise RuntimeError(
        "No VPN interface found (checked: "
        + ", ".join(VPN_INTERFACES)
        + "); VPN mode was requested but no tunnel is up"
    )
