"""Shell helper functions for OFX command execution.

This module provides shell function definitions that are prepended to
shell commands when executed. These functions provide common installation
and utility helpers that can be used in workflow commands.

Supports both Bash (Linux/macOS) and PowerShell (Windows).
"""

import os
import shutil
import sys

from ofx.settings import IS_WINDOWS, TEMP_DIR, TOOLS_BIN_DIR, TOOLS_DIR, ensure_dir


def _is_admin() -> bool:
    """Check if running with admin/root privileges."""
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def _get_sudo() -> str:
    """Get sudo prefix for Unix systems."""
    if IS_WINDOWS:
        return ""
    return "sudo" if not _is_admin() and shutil.which("sudo") else ""


def is_powershell(shell: str) -> bool:
    """Check if the shell is PowerShell."""
    shell_lower = shell.lower()
    return "powershell" in shell_lower or "pwsh" in shell_lower


def get_shell_functions(shell: str | None = None) -> str:
    """Get shell helper function definitions based on shell type.
    
    Args:
        shell: Shell executable path. Auto-detects if None.
        
    Returns:
        Shell script containing function definitions to prepend to commands.
    """
    if shell is None:
        from ofx.settings import DEFAULT_SHELL
        shell = DEFAULT_SHELL
    
    if is_powershell(shell):
        return _get_powershell_functions()
    else:
        return _get_bash_functions()


def _get_bash_functions() -> str:
    """Get Bash shell helper functions for Linux/macOS."""
    sudo = _get_sudo()
    tools_dir = str(ensure_dir(TOOLS_DIR).absolute())
    tools_bin_dir = str(ensure_dir(TOOLS_BIN_DIR).absolute())
    temp_dir = ensure_dir(TEMP_DIR).absolute().as_posix()
    python_exe = sys.executable

    return f'''# OFX Shell Helper Functions (Bash)
export OFX_TOOLS_DIR="{tools_dir}"
export OFX_TOOLS_BIN_DIR="{tools_bin_dir}"
export OFX_TEMP_DIR="{temp_dir}"
export OFX_PYTHON="{python_exe}"

fapt() {{
    if [ -z "$( ls -A /var/lib/apt/lists/ 2>/dev/null )" ]; then
        {sudo} apt-get update
    fi
    {sudo} apt-get install -y --no-install-recommends "$@"
}}

uv_install() {{
    uv tool install --python-preference managed --force --reinstall "$@"
}}

go_install() {{
    GO111MODULE=on GOBIN="{tools_bin_dir}" go install "${{1}}@latest"
}}

cargo_install() {{
    cargo install --root "{tools_dir}" "$@"
}}

npm_install() {{
    npm install -g --prefix "{tools_dir}" "$@"
}}

static_install() {{
    local url="$1"
    local name="${{2:-$(basename "$url")}}"
    curl -fSsL "$url" -o "{tools_bin_dir}/$name" && chmod +x "{tools_bin_dir}/$name"
}}

pip_install() {{
    "{python_exe}" -m pip install --upgrade "$@"
}}

# End of OFX Shell Helper Functions
'''


def _get_powershell_functions() -> str:
    """Get PowerShell helper functions for Windows."""
    tools_dir = str(ensure_dir(TOOLS_DIR).absolute())
    tools_bin_dir = str(ensure_dir(TOOLS_BIN_DIR).absolute())
    temp_dir = str(ensure_dir(TEMP_DIR).absolute())
    python_exe = sys.executable

    return f'''# OFX Shell Helper Functions (PowerShell)
$env:OFX_TOOLS_DIR = "{tools_dir}"
$env:OFX_TOOLS_BIN_DIR = "{tools_bin_dir}"
$env:OFX_TEMP_DIR = "{temp_dir}"
$env:OFX_PYTHON = "{python_exe}"

function fapt {{
    param([Parameter(ValueFromRemainingArguments=$true)]$packages)
    winget install --accept-source-agreements --accept-package-agreements $packages
}}

function uv_install {{
    param([Parameter(ValueFromRemainingArguments=$true)]$packages)
    uv tool install --python-preference managed --force --reinstall $packages
}}

function go_install {{
    param([string]$pkg)
    $env:GO111MODULE = "on"
    $env:GOBIN = "{tools_bin_dir}"
    go install "$pkg@latest"
}}

function cargo_install {{
    param([Parameter(ValueFromRemainingArguments=$true)]$packages)
    cargo install --root "{tools_dir}" $packages
}}

function npm_install {{
    param([Parameter(ValueFromRemainingArguments=$true)]$packages)
    npm install -g --prefix "{tools_dir}" $packages
}}

function static_install {{
    param([string]$url, [string]$name = $null)
    if (-not $name) {{ $name = [System.IO.Path]::GetFileName($url) }}
    $outPath = Join-Path "{tools_bin_dir}" $name
    Invoke-WebRequest -Uri $url -OutFile $outPath
}}

function pip_install {{
    param([Parameter(ValueFromRemainingArguments=$true)]$packages)
    & "{python_exe}" -m pip install --upgrade $packages
}}

# End of OFX Shell Helper Functions
'''


def get_shell_exports() -> dict[str, str]:
    """Get shell variable exports for templates.
    
    Returns:
        Dictionary of variable names to values for template resolution.
    """
    tools_dir = str(ensure_dir(TOOLS_DIR).absolute())
    tools_bin_dir = str(ensure_dir(TOOLS_BIN_DIR).absolute())
    temp_dir = ensure_dir(TEMP_DIR).absolute().as_posix()
    sudo = _get_sudo()

    return {
        "sudo": sudo,
        "tools_dir": tools_dir,
        "tools_bin_dir": tools_bin_dir,
        "temp_dir": temp_dir,
        "python": sys.executable,
        "is_windows": IS_WINDOWS,
    }
