"""Payload obfuscation engine."""

from __future__ import annotations

import base64
import random
import string
from typing import Literal

__all__ = ["obfuscate_payload", "obfuscate_cmd"]

Language = Literal[
    "php", "python", "java", "jsp", "asp", "aspx", "jscript", "bash", "powershell"
]

def _random_string(length: int = 8) -> str:
    """Generate a random variable name."""
    return "".join(random.choices(string.ascii_letters, k=length))

def _obfuscate_php(code: str) -> str:
    """Obfuscate PHP code using multiple layers."""
    b64 = base64.b64encode(code.encode()).decode()

    var_a = _random_string(4)
    var_b = _random_string(4)

    parts = ["base", "64_", "de", "code"]
    func_builder = ".".join(f"'{p}'" for p in parts)

    payload = f"""${var_a}={func_builder};${var_b}=${var_a}('{b64}');eval(${var_b});"""
    return payload

def _obfuscate_python(code: str) -> str:
    """Obfuscate Python code."""
    b64 = base64.b64encode(code.encode()).decode()
    return f"exec(__import__('base64').b64decode('{b64}').decode('utf-8'))"

def _obfuscate_java(code: str) -> str:
    """Obfuscate Java code (String fragmentation)."""
    fragments = [code[i : i + 5] for i in range(0, len(code), 5)]
    sb_var = _random_string(5)

    builder = f"StringBuilder {sb_var} = new StringBuilder();"
    for frag in fragments:
        escaped = frag.replace('"', '\\"').replace("\\", "\\\\").replace("\n", "\\n")
        builder += f'{sb_var}.append("{escaped}");'

    return f"{{ {builder} {sb_var}.toString(); }}"

def _obfuscate_asp(code: str) -> str:
    """Obfuscate ASP (VBScript) using Chr() building."""
    chars = [f"Chr({ord(c)})" for c in code]
    return "&".join(chars)

def _obfuscate_aspx(code: str) -> str:
    """Obfuscate ASPX (C#) using Unicode escape sequences."""
    return "".join(f"\\u{ord(c):04x}" for c in code)

def _obfuscate_jscript(code: str) -> str:
    """Obfuscate JScript."""
    return "".join(f"\\x{ord(c):02x}" for c in code)

def _obfuscate_bash(code: str) -> str:
    """Obfuscate Bash (Base64)."""
    b64 = base64.b64encode(code.encode()).decode()
    return f"echo {b64}|base64 -d|bash"

def _obfuscate_powershell(code: str) -> str:
    """Obfuscate PowerShell (Base64)."""
    b64 = base64.b64encode(code.encode("utf-16le")).decode()
    return f"powershell -nop -enc {b64}"

def obfuscate_cmd(command: str) -> str:
    """Obfuscate Windows CMD command using caret insertion."""
    result = []
    for char in command:
        if char in string.ascii_letters and random.random() > 0.5:
            result.append(f"{char}^")
        else:
            result.append(char)

    escaped = "".join(result).replace("^^", "^")
    if escaped.endswith("^"):
        escaped = escaped[:-1]
    return escaped

def obfuscate_payload(code: str, language: Language) -> str:
    """Obfuscate payload for specific language.

    Args:
        code: The source code/command to obfuscate
        language: Target language

    Returns:
        Obfuscated code string suitable for injection/execution
    """
    handlers = {
        "php": _obfuscate_php,
        "python": _obfuscate_python,
        "java": _obfuscate_java,
        "jsp": _obfuscate_java,
        "asp": _obfuscate_asp,
        "aspx": _obfuscate_aspx,
        "jscript": _obfuscate_jscript,
        "bash": _obfuscate_bash,
        "powershell": _obfuscate_powershell,
    }

    handler = handlers.get(language.lower())
    if not handler:
        return code

    return handler(code)
