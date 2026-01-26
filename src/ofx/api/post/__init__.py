"""Post-exploitation helper utilities."""

from __future__ import annotations

from .detect import detect_os
from .enum import linpeas_command, linux_exploit_suggester_command, winpeas_command
from .privilege import is_admin_from_whoami, is_root_from_id
from .remote import PostRemote, PostRunner, PostSSH, PostWebShell
from .transfer_remote import (
    deploy_and_run,
    download_via_scp,
    download_via_webshell,
    upload_via_scp,
    upload_via_webshell,
    upload_via_winrm,
)
from .winrm import PostWinRM
from .smbexec import PostSMBExec
from .wmiexec import PostWMIExec
from .transfer import build_download_command

__all__ = [
    "build_download_command",
    "detect_os",
    "is_admin_from_whoami",
    "is_root_from_id",
    "linpeas_command",
    "linux_exploit_suggester_command",
    "PostRemote",
    "PostRunner",
    "PostSSH",
    "PostWebShell",
    "PostWinRM",
    "PostSMBExec",
    "PostWMIExec",
    "deploy_and_run",
    "download_via_scp",
    "download_via_webshell",
    "upload_via_scp",
    "upload_via_webshell",
    "upload_via_winrm",
    "winpeas_command",
]
