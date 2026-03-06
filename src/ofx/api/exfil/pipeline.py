"""Compress-then-encrypt / decrypt-then-decompress pipeline for exfiltration."""

from __future__ import annotations

import hashlib
import struct
import zlib

__all__ = [
    "compress_encrypt",
    "decompress_decrypt",
]


def compress_encrypt(data: bytes, key: bytes) -> bytes:
    """Compress (zlib level 9) then XOR-encrypt *data* with *key*.

    Prepends a 4-byte MD5 checksum and a 4-byte original-length field so
    the receiver can verify integrity after decryption.

    Use :func:`decompress_decrypt` to reverse.
    """
    compressed = zlib.compress(data, level=9)
    key_stream = (key * (len(compressed) // len(key) + 1))[: len(compressed)]
    encrypted = bytes(a ^ b for a, b in zip(compressed, key_stream, strict=False))
    checksum = hashlib.md5(data).digest()[:4]
    return checksum + struct.pack(">I", len(data)) + encrypted


def decompress_decrypt(data: bytes, key: bytes) -> bytes:
    """Reverse of :func:`compress_encrypt`: XOR-decrypt then zlib-decompress.

    Raises:
        ValueError: On checksum or length mismatch.
    """
    checksum = data[:4]
    original_len = struct.unpack(">I", data[4:8])[0]
    encrypted = data[8:]
    key_stream = (key * (len(encrypted) // len(key) + 1))[: len(encrypted)]
    compressed = bytes(a ^ b for a, b in zip(encrypted, key_stream, strict=False))
    result = zlib.decompress(compressed)
    if len(result) != original_len:
        raise ValueError("Length mismatch after decompression")
    if hashlib.md5(result).digest()[:4] != checksum:
        raise ValueError("Checksum mismatch — data may be corrupt or tampered")
    return result
