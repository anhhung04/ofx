"""Build self-contained shell scripts from workflow jobs for detached execution.

The generated script includes all steps, environment setup, timestamped logging,
and status markers (__TASK_OK__ / __TASK_ERR__) so the session manager can
detect completion by tailing the log file.
"""

from __future__ import annotations

from ofx.models.step import RunType, Step


def build_session_script(
    steps: list[Step],
    *,
    session_id: str,
    work_dir: str,
    env: dict[str, str] | None = None,
    os_type: str = "linux",
    encrypt_at_rest: bool = False,
) -> str:
    """Generate a self-contained script that runs all steps in sequence.

    Args:
        steps: Job steps to include.
        session_id: Session identifier (embedded in markers).
        work_dir: Remote/local working directory.
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
            steps, session_id, work_dir, env or {}, encrypt_at_rest
        )
    return _build_bash(steps, session_id, work_dir, env or {}, encrypt_at_rest)


# ------------------------------------------------------------------
# Bash (Linux)
# ------------------------------------------------------------------


def _build_bash(
    steps: list[Step],
    session_id: str,
    work_dir: str,
    env: dict[str, str],
    encrypt_at_rest: bool = False,
) -> str:
    lines: list[str] = [
        "#!/bin/bash",
        f'export SESSION_ID="{session_id}"',
        f'WORK_DIR="{work_dir}"',
        'LOG_FILE="$WORK_DIR/output.log"',
        'mkdir -p "$WORK_DIR/output"',
        'cd "$WORK_DIR"',
        "",
    ]

    # Environment variables
    for key, value in env.items():
        if key in ("PATH", "HOME", "USER", "SHELL"):
            continue
        lines.append(f'export {key}="{_bash_escape(str(value))}"')
    if env:
        lines.append("")

    # Logging helper
    lines.extend(
        [
            '_log() { echo "[$(date +%Y-%m-%dT%H:%M:%S)] $*" >> "$LOG_FILE"; }',
            '_log "Session $SESSION_ID started"',
            "",
        ]
    )

    # Each step wrapped with error handling
    for idx, step in enumerate(steps):
        step_name = step.name or f"step_{idx}"
        lines.append(f'_log ">>> Step {idx}: {step_name}"')

        cmd = _step_command_bash(step, work_dir)
        if step.continue_on_error:
            lines.append(
                f'({cmd}) >> "$LOG_FILE" 2>&1 || _log "Step {idx} failed (continue_on_error)"'
            )
        else:
            lines.extend(
                [
                    f'({cmd}) >> "$LOG_FILE" 2>&1',
                    "STEP_RC=$?",
                    "if [ $STEP_RC -ne 0 ]; then",
                    f'  _log "Step {idx} FAILED (exit $STEP_RC)"',
                    '  _log "__TASK_ERR__"',
                    "  exit $STEP_RC",
                    "fi",
                ]
            )
        lines.append(f'_log "<<< Step {idx} done"')
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


def _step_command_bash(step: Step, work_dir: str) -> str:
    """Extract the shell command(s) from a step for bash."""
    run_type = step.get_run_type()
    # Always use session work_dir — step.working_directory defaults to CWD
    # which is meaningless for detached session scripts.
    cwd = work_dir

    if run_type == RunType.COMMAND:
        return f"cd {cwd} 2>/dev/null; {step.run}"

    if run_type == RunType.SCRIPT:
        # Inline script — run via heredoc
        escaped = step.script.replace("'", "'\\''")
        return f"cd {cwd} 2>/dev/null; bash -c '{escaped}'"

    if run_type == RunType.SCRIPT_FILE:
        return f"cd {cwd} 2>/dev/null; bash {step.script_file}"

    return f'echo "Unsupported run type: {run_type}"'


def _bash_escape(s: str) -> str:
    """Escape double-quotes and backslashes for bash."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


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
    env: dict[str, str],
    encrypt_at_rest: bool = False,
) -> str:
    lines: list[str] = [
        "$ErrorActionPreference = 'Stop'",
        f'$env:SESSION_ID = "{session_id}"',
        f'$WORK_DIR = "{work_dir}"',
        '$LOG_FILE = "$WORK_DIR\\output.log"',
        'New-Item -ItemType Directory -Force -Path "$WORK_DIR\\output" | Out-Null',
        "Set-Location $WORK_DIR",
        "",
    ]

    # Environment variables
    for key, value in env.items():
        if key in ("PATH", "HOME", "USER", "SHELL"):
            continue
        lines.append(f'$env:{key} = "{value}"')
    if env:
        lines.append("")

    # Log helper
    lines.extend(
        [
            'function Write-Log($msg) { "[$((Get-Date).ToString("yyyy-MM-ddTHH:mm:ss"))] $msg" | Out-File -Append -FilePath $LOG_FILE }',
            'Write-Log "Session $env:SESSION_ID started"',
            "",
        ]
    )

    for idx, step in enumerate(steps):
        step_name = step.name or f"step_{idx}"
        lines.append(f'Write-Log ">>> Step {idx}: {step_name}"')
        lines.append("try {")

        cmd = _step_command_ps(step, work_dir)
        lines.append(f"  {cmd} *>> $LOG_FILE")

        if step.continue_on_error:
            lines.append("} catch {")
            lines.append(f'  Write-Log "Step {idx} failed (continue_on_error): $_"')
            lines.append("}")
        else:
            lines.append("} catch {")
            lines.append(f'  Write-Log "Step {idx} FAILED: $_"')
            lines.append('  Write-Log "__TASK_ERR__"')
            lines.append("  exit 1")
            lines.append("}")

        lines.append(f'Write-Log "<<< Step {idx} done"')
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


def _step_command_ps(step: Step, work_dir: str) -> str:
    """Extract PowerShell command from a step."""
    run_type = step.get_run_type()
    # Always use session work_dir — step.working_directory defaults to CWD
    cwd = work_dir

    if run_type == RunType.COMMAND:
        return f'Set-Location "{cwd}"; {step.run}'

    if run_type == RunType.SCRIPT:
        escaped = step.script.replace('"', '`"')
        return f'Set-Location "{cwd}"; Invoke-Expression "{escaped}"'

    if run_type == RunType.SCRIPT_FILE:
        return f'Set-Location "{cwd}"; & "{step.script_file}"'

    return f'Write-Output "Unsupported run type: {run_type}"'
