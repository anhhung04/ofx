"""Data exfiltration helpers: DNS tunneling, HTTP chunking, and compression pipelines."""

from __future__ import annotations

from .dns import dns_decode_payload, dns_encode_payload, dns_exfil_commands
from .http import chunk_b64, http_chunks, icmp_exfil_command, reassemble_b64
from .pipeline import compress_encrypt, decompress_decrypt

__all__ = [
    "dns_encode_payload",
    "dns_decode_payload",
    "dns_exfil_commands",
    "http_chunks",
    "chunk_b64",
    "reassemble_b64",
    "icmp_exfil_command",
    "compress_encrypt",
    "decompress_decrypt",
]
