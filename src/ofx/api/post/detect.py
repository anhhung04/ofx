"""Post-exploitation detection helpers."""

from __future__ import annotations

__all__ = ["detect_os"]


def detect_os(uname_output: str) -> str:
    """Detect OS family from uname output.

    Returns:
        One of: "linux", "darwin", "windows", "unknown".
    """
    value = (uname_output or "").lower()
    if "linux" in value:
        return "linux"
    if "darwin" in value or "mac" in value:
        return "darwin"
    if "windows" in value or "mingw" in value or "cygwin" in value:
        return "windows"
    return "unknown"
