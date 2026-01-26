"""Chunking helpers."""

from __future__ import annotations

__all__ = ["chunk_string"]


def chunk_string(value: str, size: int) -> list[str]:
    """Split a string into fixed-size chunks."""
    if size <= 0:
        raise ValueError("size must be > 0")
    return [value[i : i + size] for i in range(0, len(value), size)]
