"""Lightweight packing helpers for payload transport."""

from __future__ import annotations

import gzip
from base64 import b64decode, b64encode
from io import BytesIO

__all__ = [
    "xor_pack",
    "xor_unpack",
    "gzip_pack",
    "gzip_unpack",
    "b64_gzip_pack",
    "b64_gzip_unpack",
]

def _normalize_key(key: str | bytes | bytearray | memoryview) -> bytes:
    if isinstance(key, (bytes, bytearray, memoryview)):
        return bytes(key)
    return key.encode()

def xor_pack(data: bytes, key: str | bytes) -> bytes:
    key_bytes = _normalize_key(key)
    if not key_bytes:
        raise ValueError("key must not be empty")
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))

def xor_unpack(data: bytes, key: str | bytes) -> bytes:
    return xor_pack(data, key)

def gzip_pack(data: bytes) -> bytes:
    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(data)
    return buf.getvalue()

def gzip_unpack(data: bytes) -> bytes:
    with gzip.GzipFile(fileobj=BytesIO(data), mode="rb") as f:
        return f.read()

def b64_gzip_pack(data: bytes) -> str:
    return b64encode(gzip_pack(data)).decode()

def b64_gzip_unpack(data: str) -> bytes:
    return gzip_unpack(b64decode(data))
