"""Simple encoding/obfuscation helpers."""

from __future__ import annotations

__all__ = ["rot13", "xor_bytes"]


def xor_bytes(data: bytes, key: int) -> bytes:
    """XOR bytes with a single-byte key."""
    if not 0 <= key <= 255:
        raise ValueError("key must be between 0 and 255")
    return bytes(b ^ key for b in data)


def rot13(text: str) -> str:
    """Apply ROT13 to ASCII letters."""
    trans = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
    )
    return text.translate(trans)
