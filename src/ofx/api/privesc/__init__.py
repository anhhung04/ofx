"""Privilege escalation helpers for Linux and Windows."""

from __future__ import annotations

from .linux import (
    capabilities_command,
    crontab_persistence,
    docker_escape_commands,
    kernel_exploit_check_command,
    lxd_escape_commands,
    nfs_check_commands,
    path_hijack_check_commands,
    sudo_check_command,
    suid_commands,
    writable_passwd_command,
    writable_systemd_command,
)
from .windows import (
    alwaysinstallelevated_commands,
    credential_files_commands,
    dpapi_commands,
    juicy_potato_command,
    printspoofer_command,
    registry_autorun_commands,
    token_privileges_commands,
    uac_bypass_commands,
    unquoted_service_path_command,
    weak_service_permissions_command,
)

__all__ = [
    "suid_commands",
    "capabilities_command",
    "sudo_check_command",
    "crontab_persistence",
    "writable_systemd_command",
    "docker_escape_commands",
    "lxd_escape_commands",
    "nfs_check_commands",
    "path_hijack_check_commands",
    "writable_passwd_command",
    "kernel_exploit_check_command",
    "uac_bypass_commands",
    "token_privileges_commands",
    "unquoted_service_path_command",
    "alwaysinstallelevated_commands",
    "weak_service_permissions_command",
    "credential_files_commands",
    "dpapi_commands",
    "printspoofer_command",
    "juicy_potato_command",
    "registry_autorun_commands",
]
