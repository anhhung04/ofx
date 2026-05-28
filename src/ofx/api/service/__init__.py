"""Service fingerprint helpers."""

from __future__ import annotations

import socket
import ssl
from contextlib import suppress
from dataclasses import dataclass

__all__ = ["ServiceInfo", "scan_banner", "detect_protocol"]


@dataclass(slots=True)
class ServiceInfo:
    host: str
    port: int
    banner: str | None
    tls: bool
    protocol: str | None


def _recv_banner(sock: socket.socket, max_bytes: int) -> str | None:
    try:
        data = sock.recv(max_bytes)
        return data.decode(errors="ignore").strip() if data else None
    except OSError:
        return None


def detect_protocol(port: int, banner: str | None = None) -> str | None:
    known = {
        21: "ftp",
        22: "ssh",
        25: "smtp",
        80: "http",
        110: "pop3",
        143: "imap",
        389: "ldap",
        443: "https",
        445: "smb",
        3389: "rdp",
    }
    if port in known:
        return known[port]
    if banner:
        lower = banner.lower()
        if "ssh" in lower:
            return "ssh"
        if "http" in lower or "server" in lower:
            return "http"
        if "smtp" in lower:
            return "smtp"
        if "imap" in lower:
            return "imap"
    return None


def scan_banner(
    host: str,
    port: int,
    *,
    timeout: float = 3.0,
    tls: bool | None = None,
    max_bytes: int = 1024,
) -> ServiceInfo:
    """Grab a simple banner and guess protocol."""
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        use_tls = bool(tls or port == 443)
        if use_tls:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        banner = _recv_banner(sock, max_bytes)
        proto = detect_protocol(port, banner)
        return ServiceInfo(
            host=host, port=port, banner=banner, tls=use_tls, protocol=proto
        )
    finally:
        if sock:
            with suppress(OSError):
                sock.close()
