"""Shell helper functions for OFX command execution.

This module provides shell function definitions that are prepended to
shell commands when executed. These functions provide common installation
and utility helpers that can be used in workflow commands.

Supports both Bash (Linux/macOS) and PowerShell (Windows).
"""

import logging
import os
import shutil
import sys
from pathlib import Path

from ofx.settings import (
    IS_WINDOWS,
    TEMP_DIR,
    TOOLS_BIN_DIR,
    TOOLS_DIR,
    ensure_dir,
    settings,
)

_logger = logging.getLogger("ofx.shell_functions")


def _is_admin() -> bool:
    """Check if running with admin/root privileges."""
    if IS_WINDOWS:
        try:
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore
        except Exception:
            _logger.debug("Windows admin check failed", exc_info=True)
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
    channels_dir = str(ensure_dir(Path(settings.channels_dir)).absolute())

    return f'''# Shell Helper Functions (Bash)
export TOOLS_DIR="{tools_dir}"
export TOOLS_BIN_DIR="{tools_bin_dir}"
export RUNNER_TEMP_DIR="{temp_dir}"
export RUNNER_PYTHON="{python_exe}"
export CHANNELS_DIR="{channels_dir}"

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
    GO111MODULE=on GOBIN="{tools_bin_dir}" go install "{{1}}@latest"
}}

cargo_install() {{
    cargo install --root "{tools_dir}" "$@"
}}

npm_install() {{
    npm install -g --prefix "{tools_dir}" "$@"
}}

static_install() {{
    local url="$1"
    local name="{{2:-$(basename "$url")}}"
    curl -fSsL "$url" -o "{tools_bin_dir}/$name" && chmod +x "{tools_bin_dir}/$name"
}}

pip_install() {{
    "{python_exe}" -m pip install --upgrade "$@"
}}

# --- Channel Functions (inter-job communication) ---
# Uses flock for cross-process safety (compatible with Python fcntl.flock)

ch_publish() {{
    local channel="$1"
    shift
    local data="$*"
    local channel_file="$CHANNELS_DIR/$channel"
    local lock_file="$CHANNELS_DIR/${{channel}}.lock"
    mkdir -p "$CHANNELS_DIR"
    (
        flock -x 200
        printf '%s' "$data" > "$channel_file"
    ) 200>"$lock_file"
}}

ch_get() {{
    local channel="$1"
    local channel_file="$CHANNELS_DIR/$channel"
    local lock_file="$CHANNELS_DIR/${{channel}}.lock"
    if [ ! -f "$channel_file" ]; then
        return 1
    fi
    local value
    (
        flock -s 200
        cat "$channel_file"
    ) 200>"$lock_file"
}}

ch_subscribe() {{
    local channel="$1"
    local interval="${{2:-0.1}}"
    local last_value=""
    while true; do
        local value
        value=$(ch_get "$channel" 2>/dev/null) || true
        if [ -n "$value" ] && [ "$value" != "$last_value" ]; then
            echo "$value"
            last_value="$value"
        fi
        sleep "$interval"
    done
}}

ch_wait_for() {{
    local channel="$1"
    local expected="$2"
    local timeout="${{3:-60}}"
    local interval="${{4:-0.1}}"
    local elapsed=0
    while true; do
        local value
        value=$(ch_get "$channel" 2>/dev/null) || true
        if [ -n "$value" ] && [ "$value" = "$expected" ]; then
            echo "$value"
            return 0
        fi
        sleep "$interval"
        elapsed=$(echo "$elapsed + $interval" | bc)
        if [ "$(echo "$elapsed >= $timeout" | bc)" -eq 1 ]; then
            echo "Timeout waiting for channel '$channel'" >&2
            return 1
        fi
    done
}}

# End of Shell Helper Functions
'''


def _get_powershell_functions() -> str:
    """Get PowerShell helper functions for Windows."""
    tools_dir = str(ensure_dir(TOOLS_DIR).absolute())
    tools_bin_dir = str(ensure_dir(TOOLS_BIN_DIR).absolute())
    temp_dir = str(ensure_dir(TEMP_DIR).absolute())
    python_exe = sys.executable
    channels_dir = str(ensure_dir(Path(settings.channels_dir)).absolute())

    return f'''# Shell Helper Functions (PowerShell)
$env:TOOLS_DIR = "{tools_dir}"
$env:TOOLS_BIN_DIR = "{tools_bin_dir}"
$env:RUNNER_TEMP_DIR = "{temp_dir}"
$env:RUNNER_PYTHON = "{python_exe}"
$env:CHANNELS_DIR = "{channels_dir}"

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

# --- Channel Functions (inter-job communication) ---

function ch_publish {{
    param([string]$Channel, [string]$Data)
    $dir = $env:CHANNELS_DIR
    if (-not (Test-Path $dir)) {{ New-Item -ItemType Directory -Path $dir -Force | Out-Null }}
    $channelFile = Join-Path $dir $Channel
    $lockFile = Join-Path $dir "$Channel.lock"
    $mutex = New-Object System.Threading.Mutex($false, "CH_$Channel")
    try {{
        [void]$mutex.WaitOne()
        Set-Content -Path $channelFile -Value $Data -NoNewline
    }} finally {{
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }}
}}

function ch_get {{
    param([string]$Channel)
    $dir = $env:CHANNELS_DIR
    $channelFile = Join-Path $dir $Channel
    if (-not (Test-Path $channelFile)) {{ return $null }}
    $mutex = New-Object System.Threading.Mutex($false, "CH_$Channel")
    try {{
        [void]$mutex.WaitOne()
        return Get-Content -Path $channelFile -Raw
    }} finally {{
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }}
}}

function ch_wait_for {{
    param([string]$Channel, [string]$Expected, [int]$Timeout = 60, [double]$Interval = 0.1)
    $elapsed = 0
    while ($true) {{
        $value = ch_get -Channel $Channel
        if ($value -eq $Expected) {{ return $value }}
        Start-Sleep -Milliseconds ([int]($Interval * 1000))
        $elapsed += $Interval
        if ($elapsed -ge $Timeout) {{
            Write-Error "Timeout waiting for channel '$Channel'"
            return $null
        }}
    }}
}}

# End of Shell Helper Functions
'''


def get_shell_exports() -> dict[str, str | bool]:
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
