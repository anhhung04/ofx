"""Builtin ``shell`` module: execute shell commands.

This is the single code path for ``module: shell`` steps: :class:`ModuleRunner`
invokes :func:`run` with a :class:`~ofx.modules.base.ModuleContext`, locally,
and the module must stay self-contained (stdlib plus :mod:`ofx.modules.base`)
so its source can be streamed for remote execution. The shell-helper preamble
(``log_info``, ``fapt``, ``ch_publish``, …) is generated inline here instead of
importing :mod:`ofx.settings`.

Behavior mirrors the removed ``CommandRunner``/``CommandExecutor``: process
groups are spawned with ``start_new_session`` and killed as a group on
timeout/cancel, stdout/stderr are truncated at ``OFX_MAX_OUTPUT_SIZE``, and
``key=value`` lines written to ``$RUNNER_OUTPUTS`` are merged into the result
outputs (the step runner owns cleanup of that file).
"""

from __future__ import annotations

import base64
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from contextlib import suppress
from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleContext, ModuleResult

name = "shell"
description = "Execute a shell command (equivalent to a legacy ``run:`` step)."
args_schema: dict[str, Any] = {
    "cmd": {
        "type": "string",
        "description": "Shell command to execute",
        "required": True,
    },
    "shell": {"type": "string", "description": "Shell to use"},
    "working_directory": {"type": "string", "description": "Working directory"},
    "timeout_minutes": {"type": "integer", "description": "Timeout in minutes"},
    "interactive": {
        "type": "boolean",
        "description": "Interactive stdin/stdout passthrough",
    },
}

DEFAULT_SHELL = "powershell.exe" if os.name == "nt" else "/bin/bash"
"""Shell used when none is provided (mirrors ``ofx.settings.DEFAULT_SHELL``)."""

_TIMEOUT_EXIT_CODE = 124
"""Exit code reported when a command exceeds its timeout (GNU ``timeout``)."""

_INTERACTIVE_STDOUT = "[Interactive mode - output shown in real-time]"
"""Placeholder stdout returned for interactive executions (no capture)."""

# Fresh per-process temp dir, mirroring ``ofx.settings.TEMP_DIR`` (created at
# import time there, so exports stay stable for the lifetime of the process).
_TEMP_DIR = Path(tempfile.mkdtemp(prefix=".tmp_r_", dir=tempfile.gettempdir()))


def _default_max_output_size() -> int:
    """Return the output truncation cap (bytes), honoring the settings env var."""
    try:
        return int(os.environ.get("OFX_MAX_OUTPUT_SIZE", 10 * 1024 * 1024))
    except ValueError:
        return 10 * 1024 * 1024


def _is_admin() -> bool:
    """Check if running with admin/root privileges."""
    if os.name == "nt":
        try:
            import ctypes

            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _get_sudo() -> str:
    """Get the sudo prefix for Unix systems ("" on Windows or as root)."""
    if os.name == "nt":
        return ""
    return "sudo" if not _is_admin() and shutil.which("sudo") else ""


def _is_powershell(shell: str) -> bool:
    """Return whether *shell* is PowerShell."""
    shell_lower = shell.lower()
    return "powershell" in shell_lower or "pwsh" in shell_lower


def get_shell_functions(shell: str | None = None, *, channels_dir: str | None = None) -> str:
    """Build the shell-helper preamble prepended to executed commands.

    Exports ``TOOLS_DIR``/``TOOLS_BIN_DIR`` (``~/Tools``), the per-process
    ``RUNNER_TEMP_DIR``, ``RUNNER_PYTHON`` and ``CHANNELS_DIR``, then defines
    the install/utility/channel helper functions. Paths are derived from the
    environment with stdlib only so the module stays self-contained.
    """
    if shell is None:
        shell = DEFAULT_SHELL
    if _is_powershell(shell):
        return _powershell_functions(channels_dir=channels_dir)
    return _bash_functions(channels_dir=channels_dir)


def _bash_functions(*, channels_dir: str | None) -> str:
    """Build the Bash (Linux/macOS) helper preamble."""
    sudo = _get_sudo()
    tools_dir = str(Path.home() / "Tools")
    tools_bin_dir = str(Path.home() / "Tools" / "bin")
    temp_dir = _TEMP_DIR.as_posix()
    python_exe = sys.executable
    channels = str(Path(channels_dir) if channels_dir else _TEMP_DIR / "channels")

    return f'''# Shell Helper Functions (Bash)
export TOOLS_DIR="{tools_dir}"
export TOOLS_BIN_DIR="{tools_bin_dir}"
export RUNNER_TEMP_DIR="{temp_dir}"
export RUNNER_PYTHON="{python_exe}"
export CHANNELS_DIR="{channels}"

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

'''


def _powershell_functions(*, channels_dir: str | None) -> str:
    """Build the PowerShell (Windows) helper preamble."""
    tools_dir = str(Path.home() / "Tools")
    tools_bin_dir = str(Path.home() / "Tools" / "bin")
    temp_dir = str(_TEMP_DIR)
    python_exe = sys.executable
    channels = str(Path(channels_dir) if channels_dir else _TEMP_DIR / "channels")

    return f'''# Shell Helper Functions (PowerShell)
$env:TOOLS_DIR = "{tools_dir}"
$env:TOOLS_BIN_DIR = "{tools_bin_dir}"
$env:RUNNER_TEMP_DIR = "{temp_dir}"
$env:RUNNER_PYTHON = "{python_exe}"
$env:CHANNELS_DIR = "{channels}"

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

'''


def get_shell_exports() -> dict[str, str | bool]:
    """Get shell variable exports for template resolution.

    Mirrors the former :mod:`ofx.modules.execution.shell_functions` helper
    using stdlib-only path derivation (self-contained module).
    """
    return {
        "sudo": _get_sudo(),
        "tools_dir": str(Path.home() / "Tools"),
        "tools_bin_dir": str(Path.home() / "Tools" / "bin"),
        "temp_dir": _TEMP_DIR.as_posix(),
        "python": sys.executable,
        "is_windows": platform.system() == "Windows",
    }


# ---------------------------------------------------------------------------
# Process-group cleanup
# ---------------------------------------------------------------------------


def _reap_process_group(pgid: int) -> None:
    """Reap zombie processes in a group so the process table stays clean."""
    try:
        while True:
            wpid, _status = os.waitpid(-pgid, os.WNOHANG)
            if wpid == 0:
                break
    except ChildProcessError:
        pass


def _process_group_id(proc: subprocess.Popen[Any]) -> int | None:
    """Return the child's own process group id, or ``None`` when unsafe.

    ``start_new_session=True`` makes the child its group leader. Never signal
    a shared group (especially the test runner or its parent agent).
    """
    pid = getattr(proc, "pid", None)
    if type(pid) is not int or pid <= 1:
        return None

    try:
        pgid = os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return None

    return pgid if pgid == pid and pgid != os.getpgrp() else None


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """SIGTERM the process group, then SIGKILL if it is still alive.

    Spawns use ``start_new_session=True`` so grandchildren (e.g. nmap spawned
    by bash) are cleaned up too; zombies are reaped afterwards.
    """
    pgid = _process_group_id(proc)
    if pgid is None:
        return

    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGTERM)

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except (OSError, ProcessLookupError):
            _reap_process_group(pgid)
            return
        time.sleep(0.1)
    try:
        os.killpg(pgid, 0)
    except (OSError, ProcessLookupError):
        _reap_process_group(pgid)
        return

    with suppress(OSError, ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)

    _reap_process_group(pgid)


# ---------------------------------------------------------------------------
# Output decoding / RUNNER_OUTPUTS
# ---------------------------------------------------------------------------


def _decode_output(
    stdout_bytes: bytes, stderr_bytes: bytes, max_size: int
) -> tuple[str, str, dict[str, Any]]:
    """Decode captured bytes with truncation and binary fallback."""
    outputs: dict[str, Any] = {}

    try:
        stdout = stdout_bytes.decode("utf-8").strip()
        if len(stdout_bytes) > max_size:
            outputs["output_truncated"] = True
            stdout = (
                stdout_bytes[:max_size].decode("utf-8", errors="ignore")
                + "\n... [OUTPUT TRUNCATED]"
            )

        stderr = stderr_bytes.decode("utf-8").strip()
        if len(stderr_bytes) > max_size:
            outputs["stderr_truncated"] = True
            stderr = (
                stderr_bytes[:max_size].decode("utf-8", errors="ignore")
                + "\n... [STDERR TRUNCATED]"
            )
    except UnicodeDecodeError:
        outputs["binary_output"] = True
        stdout = base64.b64encode(stdout_bytes).decode("utf-8")
        if len(stdout_bytes) > max_size:
            outputs["output_truncated"] = True
            stdout = (
                base64.b64encode(stdout_bytes[:max_size]).decode("utf-8")
                + "... [BINARY OUTPUT TRUNCATED]"
            )

        stderr = base64.b64encode(stderr_bytes).decode("utf-8")
        if len(stderr_bytes) > max_size:
            outputs["stderr_truncated"] = True
            stderr = (
                base64.b64encode(stderr_bytes[:max_size]).decode("utf-8")
                + "... [BINARY STDERR TRUNCATED]"
            )

    return stdout, stderr, outputs


def capture_outputs_file(ctx: ModuleContext) -> dict[str, str]:
    """Parse ``key=value`` lines from the RUNNER_OUTPUTS file (no delete).

    Step cleanup owns the file (StepExecutor removes it in ``post_run`` /
    ``on_failure``); the builtin only reads and merges.
    """
    outputs_file = ctx.env.get("RUNNER_OUTPUTS") or ctx.env.get("OFX_OUTPUTS")
    if not outputs_file:
        return {}
    path = Path(str(outputs_file))
    if not path.exists():
        return {}

    parsed: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key_name, value = line.split("=", 1)
            key_name = key_name.strip()
            value = value.strip()
            if not key_name:
                continue
            parsed[key_name] = value
            ctx.log(f"Captured output: {key_name}={value}")
    except Exception as exc:
        ctx.log(f"Failed to parse RUNNER_OUTPUTS: {exc}")
    return parsed


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _spawn(
    full_cmd: str,
    *,
    shell: str,
    working_directory: Path,
    env: dict[str, str],
    **overrides: Any,
) -> subprocess.Popen[Any]:
    """Spawn *full_cmd* in its own process group."""
    kwargs: dict[str, Any] = {
        "executable": shell,
        "cwd": working_directory,
        "env": env,
        "start_new_session": True,
    }
    kwargs.update(overrides)
    return subprocess.Popen(full_cmd, shell=True, **kwargs)


def _timeout_result(timeout_minutes: float, ctx: ModuleContext) -> ModuleResult:
    """Build the timeout result (exit code 124) plus any partial captures."""
    outputs: dict[str, Any] = {}
    outputs.update(capture_outputs_file(ctx))
    minutes = f"{timeout_minutes:g}"
    return ModuleResult(
        exit_code=_TIMEOUT_EXIT_CODE,
        stderr=f"Command timed out after {minutes} minutes",
        outputs=outputs,
    )


def run(ctx: ModuleContext) -> ModuleResult:
    """Execute the command synchronously (single code path for shell steps)."""
    cmd = str(ctx.args.get("cmd", ""))
    if not cmd:
        return ModuleResult(exit_code=1, stderr="shell module requires 'cmd' in args")
    shell = str(ctx.args.get("shell", DEFAULT_SHELL))
    if not shell or not Path(shell).exists():
        return ModuleResult(exit_code=1, stderr=f"Shell not found: {shell}")
    working_directory = Path(ctx.args.get("working_directory", ctx.working_directory))
    timeout_minutes = float(ctx.args.get("timeout_minutes", 1440))
    timeout_seconds = timeout_minutes * 60
    env = {**os.environ, **{str(key): str(value) for key, value in ctx.env.items()}}
    full_cmd = (
        f"{get_shell_functions(shell, channels_dir=str(ctx.channels_dir) if ctx.channels_dir else None)}\n{cmd}"
    )

    interactive = bool(
        ctx.interactive
        and str(ctx.env.get("OFX_ALLOW_INTERACTIVE") or "").lower()
        in ("1", "true", "yes", "on")
    )

    try:
        if interactive:
            return _run_interactive(
                full_cmd,
                shell=shell,
                working_directory=working_directory,
                env=env,
                timeout_seconds=timeout_seconds,
                timeout_minutes=timeout_minutes,
                ctx=ctx,
            )
        return _run_non_interactive(
            full_cmd,
            shell=shell,
            working_directory=working_directory,
            env=env,
            timeout_seconds=timeout_seconds,
            timeout_minutes=timeout_minutes,
            ctx=ctx,
        )
    except Exception:
        return ModuleResult(exit_code=1, stderr=traceback.format_exc())


def _run_interactive(
    full_cmd: str,
    *,
    shell: str,
    working_directory: Path,
    env: dict[str, str],
    timeout_seconds: float,
    timeout_minutes: float,
    ctx: ModuleContext,
) -> ModuleResult:
    """Run with real stdin/stdout/stderr (no capture) in the child's group."""
    proc = _spawn(
        full_cmd,
        shell=shell,
        working_directory=working_directory,
        env=env,
        stdin=sys.__stdin__ or sys.stdin,
        stdout=sys.__stdout__ or sys.stdout,
        stderr=sys.__stderr__ or sys.stderr,
    )
    try:
        exit_code = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        proc.wait()
        return _timeout_result(timeout_minutes, ctx)
    return ModuleResult(
        exit_code=exit_code,
        stdout=_INTERACTIVE_STDOUT,
    )


def _run_non_interactive(
    full_cmd: str,
    *,
    shell: str,
    working_directory: Path,
    env: dict[str, str],
    timeout_seconds: float,
    timeout_minutes: float,
    ctx: ModuleContext,
) -> ModuleResult:
    """Run with captured pipes, streaming stdout lines to ``ctx.log``."""
    proc = _spawn(
        full_cmd,
        shell=shell,
        working_directory=working_directory,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        if ctx.logger is not None:
            exit_code, stdout, stderr, flags = _stream_capture(proc, ctx, timeout_seconds)
        else:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
            stdout, stderr, flags = _decode_output(
                stdout_bytes, stderr_bytes, _default_max_output_size()
            )
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        proc.wait()
        return _timeout_result(timeout_minutes, ctx)
    outputs: dict[str, Any] = dict(flags)
    outputs.update(capture_outputs_file(ctx))
    return ModuleResult(exit_code=exit_code, stdout=stdout, stderr=stderr, outputs=outputs)


def _stream_capture(
    proc: subprocess.Popen[Any],
    ctx: ModuleContext,
    timeout_seconds: float,
) -> tuple[int | None, str, str, dict[str, Any]]:
    """Read stdout line-by-line (streaming to ctx.log) and stderr in full.

    Both pipes are drained by reader threads so the timeout applies from spawn
    (a blocking main-thread read would swallow it until the child exits).
    Raises :class:`subprocess.TimeoutExpired` after killing the process group
    when *proc* does not finish within *timeout_seconds*; the caller converts
    that into the timeout result.
    """
    max_size = _default_max_output_size()
    stdout_lines: list[str] = []
    stdout_bytes_total = 0
    _stream_lock = threading.Lock()
    stderr_holder: list[bytes] = []

    def _stdout_reader() -> None:
        nonlocal stdout_bytes_total
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            try:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
            except Exception:
                line = raw_line.hex()
            with _stream_lock:
                stdout_bytes_total += len(raw_line)
                if stdout_bytes_total <= max_size:
                    stdout_lines.append(line)
            try:
                ctx.log(line)
            except Exception:
                pass

    def _stderr_reader() -> None:
        assert proc.stderr is not None
        stderr_holder.append(proc.stderr.read())

    stdout_thread = threading.Thread(target=_stdout_reader, daemon=True)
    stderr_thread = threading.Thread(target=_stderr_reader, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        exit_code = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        proc.wait()
        raise
    finally:
        stdout_thread.join(timeout=5.0)
        stderr_thread.join(timeout=5.0)

    stderr_bytes = stderr_holder[0] if stderr_holder else b""
    try:
        stderr = stderr_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        stderr = base64.b64encode(stderr_bytes).decode("utf-8")

    outputs: dict[str, Any] = {}
    stdout = "\n".join(stdout_lines)
    if stdout_bytes_total > max_size:
        stdout += "\n... [OUTPUT TRUNCATED]"
        outputs["output_truncated"] = True
    if len(stderr_bytes) > max_size:
        outputs["stderr_truncated"] = True
        stderr = (
            stderr_bytes[:max_size].decode("utf-8", errors="ignore")
            + "\n... [STDERR TRUNCATED]"
        )
    return exit_code, stdout, stderr, outputs


__all__ = [
    "DEFAULT_SHELL",
    "args_schema",
    "capture_outputs_file",
    "description",
    "get_shell_exports",
    "kill_process_tree",
    "name",
    "run",
    "get_shell_functions",
]
