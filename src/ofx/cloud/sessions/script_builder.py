"""Build self-contained shell scripts from workflow steps for detached execution.

The generated script includes all steps, environment setup, timestamped logging,
and status markers (__TASK_OK__ / __TASK_ERR__) so the session manager can
detect completion by tailing the log file.
"""

from __future__ import annotations

import re

from ofx.cloud.task_runtime import build_task_command_from_step
from ofx.models.step import RunType, Step

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_env_key(key: str) -> None:
    """Validate environment variable names used in generated session scripts."""
    if not _ENV_KEY_RE.fullmatch(key):
        raise ValueError(
            f"Invalid environment variable name: {key!r}. "
            "Expected [A-Za-z_][A-Za-z0-9_]*."
        )


def build_session_script(
    steps: list[Step],
    *,
    session_id: str,
    work_dir: str,
    workflow_name: str = "",
    job_name: str = "",
    env: dict[str, str] | None = None,
    os_type: str = "linux",
    encrypt_at_rest: bool = False,
) -> str:
    """Generate a self-contained script that runs all steps in sequence.

    Args:
        steps: Job steps to include.
        session_id: Session identifier (embedded in markers).
        work_dir: Remote/local working directory.
        workflow_name: Workflow display name for log context.
        job_name: Job display name/id for log context.
        env: Extra environment variables to export.
        os_type: "linux" (bash) or "windows" (powershell).
        encrypt_at_rest: If True, appends an encryption epilogue that tars
            and encrypts the ``output/`` directory using a key file at
            ``$WORK_DIR/.skey``, then shreds the originals.

    Returns:
        Script content as a string.
    """
    if os_type == "windows":
        return _build_powershell(
            steps, session_id, work_dir, workflow_name, job_name, env or {}, encrypt_at_rest
        )
    return _build_bash(
        steps, session_id, work_dir, workflow_name, job_name, env or {}, encrypt_at_rest
    )


# ------------------------------------------------------------------
# Bash (Linux)
# ------------------------------------------------------------------


def _build_bash(
    steps: list[Step],
    session_id: str,
    work_dir: str,
    workflow_name: str,
    job_name: str,
    env: dict[str, str],
    encrypt_at_rest: bool = False,
) -> str:
    scope = _bash_escape(job_name or "full-workflow")
    workflow = _bash_escape(workflow_name or "")
    lines: list[str] = [
        "#!/bin/bash",
        f'export SESSION_ID="{_bash_escape(session_id)}"',
        f'WORK_DIR="{_bash_escape(work_dir)}"',
        'LOG_FILE="$WORK_DIR/output.log"',
        'mkdir -p "$WORK_DIR/output"',
        'cd "$WORK_DIR"',
        "",
    ]

    # Environment variables
    for key, value in env.items():
        _validate_env_key(key)
        if key in ("PATH", "HOME", "USER", "SHELL"):
            continue
        lines.append(f'export {key}="{_bash_escape(str(value))}"')
    if env:
        lines.append("")

    # Logging helper
    lines.extend(
        [
            '_log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*" >> "$LOG_FILE"; }',
            f'_log "Session $SESSION_ID started (workflow={workflow} job={scope})"',
            "",
        ]
    )

    # Each step wrapped with error handling
    for idx, step in enumerate(steps):
        step_desc = _bash_escape(_step_log_descriptor(step, idx))
        lines.append(f'_log ">>> Step {idx}: {step_desc}"')

        cmd = _step_command_bash(step, idx, work_dir)
        if step.continue_on_error:
            lines.append(
                f'({cmd}) >> "$LOG_FILE" 2>&1 || _log "Step {idx} ({step_desc}) failed (continue_on_error)"'
            )
        else:
            lines.extend(
                [
                    f'({cmd}) >> "$LOG_FILE" 2>&1',
                    "STEP_RC=$?",
                    "if [ $STEP_RC -ne 0 ]; then",
                    f'  _log "Step {idx} ({step_desc}) FAILED (exit $STEP_RC)"',
                    '  _log "__TASK_ERR__"',
                    "  exit $STEP_RC",
                    "fi",
                ]
            )
        lines.append(f'_log "<<< Step {idx} ({step_desc}) done"')
        lines.append("")

    if encrypt_at_rest:
        lines.extend(_bash_encrypt_epilogue())

    lines.extend(
        [
            '_log "All steps completed successfully"',
            '_log "__TASK_OK__"',
        ]
    )

    # Self-shred AFTER markers are written so bash can finish cleanly.
    # Must come last — shred overwrites file content on disk and bash
    # may not have buffered the rest of the script yet.
    if encrypt_at_rest:
        lines.extend(
            [
                "",
                "# Self-destruct (after markers written)",
                'shred -u "$WORK_DIR/run.sh" 2>/dev/null || rm -f "$WORK_DIR/run.sh"',
            ]
        )

    return "\n".join(lines) + "\n"


def _step_command_bash(step: Step, step_index: int, work_dir: str) -> str:  # noqa: ARG001
    """Extract the shell command(s) from a step for bash.

    Uses ``$WORK_DIR`` rather than hard-coding *work_dir* so that paths with
    spaces continue to work (the outer script always sets WORK_DIR as a
    quoted double-quoted assignment).
    """
    run_type = step.get_run_type()

    if run_type == RunType.COMMAND:
        return f'cd "$WORK_DIR" 2>/dev/null; {step.run}'

    if run_type == RunType.SCRIPT:
        script_name = _python_step_filename(step_index)
        escaped_name = _bash_escape(script_name)
        return (
            'cd "$WORK_DIR" 2>/dev/null; '
            "__OFX_PY_BIN=$(command -v python3 || command -v python); "
            'if [ -z "$__OFX_PY_BIN" ]; then echo "Python interpreter not found" >&2; exit 127; fi; '
            f'"$__OFX_PY_BIN" "{escaped_name}"'
        )

    if run_type == RunType.SCRIPT_FILE:
        script_name = _python_step_filename(step_index)
        escaped_name = _bash_escape(script_name)
        return (
            'cd "$WORK_DIR" 2>/dev/null; '
            "__OFX_PY_BIN=$(command -v python3 || command -v python); "
            'if [ -z "$__OFX_PY_BIN" ]; then echo "Python interpreter not found" >&2; exit 127; fi; '
            f'"$__OFX_PY_BIN" "{escaped_name}"'
        )

    if run_type == RunType.TASK:
        return f'cd "$WORK_DIR" 2>/dev/null; {build_task_command_from_step(step)}'

    return f'echo "Unsupported run type: {run_type}"'


def _bash_escape(s: str) -> str:
    """Escape double-quotes and backslashes for bash."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def _python_step_filename(step_index: int) -> str:
    """Return deterministic filename for staged inline step scripts."""
    return f".ofx_step_{step_index}.py"


def _step_log_descriptor(step: Step, step_index: int) -> str:
    """Build a consistent, human-readable step descriptor for logs."""
    step_name = step.name or f"step_{step_index}"
    run_type = step.get_run_type().value
    return f"{step_name} [{run_type}]"


def _bash_encrypt_epilogue() -> list[str]:
    """Return bash lines that encrypt the output/ directory at rest.

    Expects a key file at ``$WORK_DIR/.skey`` written by the session
    manager before launch.  After encryption the original output dir, the
    tar archive, and the key file are securely deleted.
    """
    return [
        "",
        "# ---- At-rest encryption ----",
        'KEY_FILE="$WORK_DIR/.skey"',
        'if [ -f "$KEY_FILE" ] && [ -d "$WORK_DIR/output" ]; then',
        '  _log "Encrypting output at rest..."',
        '  tar czf "$WORK_DIR/output.tar.gz" -C "$WORK_DIR" output >> "$LOG_FILE" 2>&1',
        "  TAR_RC=$?",
        "  if [ $TAR_RC -eq 0 ]; then",
        "    openssl enc -aes-256-cbc -pbkdf2 -iter 100000 "
        '-pass "file:$KEY_FILE" '
        '-in "$WORK_DIR/output.tar.gz" '
        '-out "$WORK_DIR/output.enc" >> "$LOG_FILE" 2>&1',
        "    ENC_RC=$?",
        "    if [ $ENC_RC -eq 0 ]; then",
        '      chmod 600 "$WORK_DIR/output.enc"',
        '      rm -rf "$WORK_DIR/output" "$WORK_DIR/output.tar.gz"',
        '      shred -u "$KEY_FILE" 2>/dev/null || rm -f "$KEY_FILE"',
        '      _log "Output encrypted -> output.enc"',
        "    else",
        '      _log "WARNING: openssl encryption failed (rc=$ENC_RC); output left unencrypted"',
        '      rm -f "$WORK_DIR/output.tar.gz"',
        "    fi",
        "  else",
        '    _log "WARNING: tar failed (rc=$TAR_RC); output left unencrypted"',
        "  fi",
        "else",
        '  _log "WARNING: No key file or no output — skipping at-rest encryption"',
        "fi",
        "",
    ]


# ------------------------------------------------------------------
# PowerShell (Windows)
# ------------------------------------------------------------------


def _build_powershell(
    steps: list[Step],
    session_id: str,
    work_dir: str,
    workflow_name: str,
    job_name: str,
    env: dict[str, str],
    encrypt_at_rest: bool = False,
) -> str:
    scope = _ps_escape(job_name or "full-workflow")
    workflow = _ps_escape(workflow_name or "")
    lines: list[str] = [
        "$ErrorActionPreference = 'Stop'",
        f'$env:SESSION_ID = "{_ps_escape(session_id)}"',
        f'$WORK_DIR = "{_ps_escape(work_dir)}"',
        '$LOG_FILE = "$WORK_DIR\\output.log"',
        'New-Item -ItemType Directory -Force -Path "$WORK_DIR\\output" | Out-Null',
        "Set-Location $WORK_DIR",
        "",
    ]

    # Environment variables
    for key, value in env.items():
        _validate_env_key(key)
        if key in ("PATH", "HOME", "USER", "SHELL"):
            continue
        lines.append(f'$env:{key} = "{_ps_escape(str(value))}"')
    if env:
        lines.append("")

    # Log helper
    lines.extend(
        [
            'function Write-Log($msg) { "[$((Get-Date).ToString("yyyy-MM-ddTHH:mm:ss"))] $msg" | Out-File -Append -FilePath $LOG_FILE }',
            f'Write-Log "Session $env:SESSION_ID started (workflow={workflow} job={scope})"',
            "",
        ]
    )

    for idx, step in enumerate(steps):
        step_desc = _ps_escape(_step_log_descriptor(step, idx))
        lines.append(f'Write-Log ">>> Step {idx}: {step_desc}"')
        lines.append("try {")

        cmd = _step_command_ps(step, idx, work_dir)
        lines.append(f"  {cmd} *>> $LOG_FILE")

        if step.continue_on_error:
            lines.append("} catch {")
            lines.append(
                f'  Write-Log "Step {idx} ({step_desc}) failed (continue_on_error): $_"'
            )
            lines.append("}")
        else:
            lines.append("} catch {")
            lines.append(f'  Write-Log "Step {idx} ({step_desc}) FAILED: $_"')
            lines.append('  Write-Log "__TASK_ERR__"')
            lines.append("  exit 1")
            lines.append("}")

        lines.append(f'Write-Log "<<< Step {idx} ({step_desc}) done"')
        lines.append("")

    if encrypt_at_rest:
        lines.extend(_ps_encrypt_epilogue())

    lines.extend(
        [
            'Write-Log "All steps completed successfully"',
            'Write-Log "__TASK_OK__"',
        ]
    )

    # Self-destruct AFTER markers are written
    if encrypt_at_rest:
        lines.extend(
            [
                "",
                "# Self-destruct (after markers written)",
                'Remove-Item -Force "$WORK_DIR\\run.ps1" -ErrorAction SilentlyContinue',
            ]
        )

    return "\n".join(lines) + "\n"


def _ps_encrypt_epilogue() -> list[str]:
    r"""Return PowerShell lines that encrypt the output\ directory at rest.

    Uses .NET AES encryption via a key file at ``$WORK_DIR\.skey``.
    """
    return [
        "",
        "# ---- At-rest encryption ----",
        '$KeyFile = "$WORK_DIR\\.skey"',
        'if ((Test-Path $KeyFile) -and (Test-Path "$WORK_DIR\\output")) {',
        '  Write-Log "Encrypting output at rest..."',
        "  try {",
        '    Compress-Archive -Path "$WORK_DIR\\output\\*" -DestinationPath "$WORK_DIR\\output.zip" -Force',
        "    $keyBytes = [System.Text.Encoding]::UTF8.GetBytes((Get-Content $KeyFile -Raw).Trim())",
        "    # Derive 32-byte AES key via SHA256",
        "    $sha = [System.Security.Cryptography.SHA256]::Create()",
        "    $aesKey = $sha.ComputeHash($keyBytes)",
        '    $plainBytes = [System.IO.File]::ReadAllBytes("$WORK_DIR\\output.zip")',
        "    $aes = [System.Security.Cryptography.Aes]::Create()",
        "    $aes.Key = $aesKey",
        "    $aes.GenerateIV()",
        "    $enc = $aes.CreateEncryptor()",
        "    $cipherBytes = $enc.TransformFinalBlock($plainBytes, 0, $plainBytes.Length)",
        "    # Write: [16-byte IV][ciphertext]",
        '    $outStream = [System.IO.File]::Create("$WORK_DIR\\output.enc")',
        "    $outStream.Write($aes.IV, 0, $aes.IV.Length)",
        "    $outStream.Write($cipherBytes, 0, $cipherBytes.Length)",
        "    $outStream.Close()",
        '    Remove-Item -Recurse -Force "$WORK_DIR\\output"',
        '    Remove-Item -Force "$WORK_DIR\\output.zip"',
        "    Remove-Item -Force $KeyFile",
        '    Write-Log "Output encrypted -> output.enc"',
        "  } catch {",
        '    Write-Log "WARNING: Encryption failed: $_"',
        '    Remove-Item -Force "$WORK_DIR\\output.zip" -ErrorAction SilentlyContinue',
        "  }",
        "} else {",
        '  Write-Log "WARNING: No key file or no output -- skipping at-rest encryption"',
        "}",
        "",
    ]


def _ps_escape(s: str) -> str:
    """Escape a string for safe embedding inside PowerShell double-quoted strings.

    Escapes backticks (PS escape char), double-quotes, and dollar signs so that
    the value is treated literally rather than expanded or misinterpreted.
    """
    return (
        s
        .replace("`", "``")
        .replace('"', '`"')
        .replace("$", "`$")
    )


def _step_command_ps(step: Step, step_index: int, work_dir: str) -> str:
    """Extract PowerShell command from a step.

    For inline scripts the content is written to a here-string variable
    and piped to a temp script file, avoiding double-quote and backtick
    escaping issues inside ``Invoke-Expression``.
    """
    run_type = step.get_run_type()
    escaped_cwd = _ps_escape(work_dir)

    if run_type == RunType.COMMAND:
        return f'Set-Location "{escaped_cwd}"; {step.run}'

    if run_type == RunType.SCRIPT:
        script_name = _python_step_filename(step_index)
        return (
            f'Set-Location "{escaped_cwd}"; '
            f'$__ofx_py = Join-Path $WORK_DIR "{_ps_escape(script_name)}"; '
            "if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 $__ofx_py } "
            "elseif (Get-Command python -ErrorAction SilentlyContinue) { & python $__ofx_py } "
            "elseif (Get-Command python3 -ErrorAction SilentlyContinue) { & python3 $__ofx_py } "
            'else { throw "Python interpreter not found" }; '
            "$__ofx_rc = $LASTEXITCODE; if ($__ofx_rc -ne 0) { exit $__ofx_rc }"
        )

    if run_type == RunType.SCRIPT_FILE:
        script_name = _python_step_filename(step_index)
        return (
            f'Set-Location "{escaped_cwd}"; '
            f'$__ofx_py = Join-Path $WORK_DIR "{_ps_escape(script_name)}"; '
            "if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 $__ofx_py } "
            "elseif (Get-Command python -ErrorAction SilentlyContinue) { & python $__ofx_py } "
            "elseif (Get-Command python3 -ErrorAction SilentlyContinue) { & python3 $__ofx_py } "
            'else { throw "Python interpreter not found" }; '
            "$__ofx_rc = $LASTEXITCODE; "
            "if ($__ofx_rc -ne 0) { exit $__ofx_rc }"
        )

    if run_type == RunType.TASK:
        return f'Set-Location "{escaped_cwd}"; {build_task_command_from_step(step)}'

    return f'Write-Output "Unsupported run type: {run_type}"'
