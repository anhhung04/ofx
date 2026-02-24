"""Helpers to craft persistence commands for remote runners."""

from __future__ import annotations

from pathlib import PureWindowsPath

__all__ = [
    "schtask_command",
    "service_command",
    "runkey_command",
]


def schtask_command(name: str, cmd: str, *, trigger: str = "ONLOGON", user: str | None = None) -> str:
    target_user = f"/RU {user}" if user else "/RU SYSTEM"
    return " ".join(
        [
            "schtasks /Create /F",
            f"/SC {trigger}",
            f"/TN {name}",
            f"/TR \"{cmd}\"",
            target_user,
        ]
    )


def service_command(name: str, bin_path: str, *, display_name: str | None = None) -> str:
    disp = display_name or name
    sanitized = PureWindowsPath(bin_path)
    return " ".join(
        [
            "sc create",
            name,
            f"binPath= \"{sanitized}\"",
            f"DisplayName= \"{disp}\"",
            "start= auto",
        ]
    )


def runkey_command(name: str, value: str, *, hive: str = "HKCU") -> str:
    key = rf"{hive}\Software\Microsoft\Windows\CurrentVersion\Run"
    return rf'reg add "{key}" /v "{name}" /t REG_SZ /d "{value}" /f'
