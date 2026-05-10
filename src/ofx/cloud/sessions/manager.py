"""Session lifecycle manager — submit, status, fetch, cancel, destroy.

Orchestrates both **local** (background subprocess) and **cloud** (VPS) sessions.
"""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import shlex
import shutil
import signal
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.encryption import decrypt_results, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.store import SessionStore

logger = logging.getLogger("ofx")

_DONE_MARKER = "__TASK_OK__"
_FAIL_MARKER = "__TASK_ERR__"

_INITIAL_POLL_INTERVAL = 10.0    # seconds before first retry
_MAX_POLL_INTERVAL = 120.0       # 2 minutes max between retries
_POLL_BACKOFF_FACTOR = 1.5       # multiply interval on each failure
_MAX_CONSECUTIVE_FAILURES = 10   # mark session as unreachable after N failures
_SSH_COMMAND_TIMEOUT = 30        # seconds for individual SSH commands during polling


def _inputs_to_env(inputs: dict[str, Any]) -> dict[str, str]:
    """Convert session inputs dict to environment variable entries.

    Each key is uppercased and prefixed with ``INPUT_`` so it becomes
    accessible inside session scripts as e.g. ``$INPUT_TARGETS_FILE``.
    The original lowercased key is also exported for convenience.

    File-valued inputs (strings pointing to existing local paths) are
    exported as-is; the caller is responsible for uploading the file to
    the remote host when needed.

    Args:
        inputs: Workflow input dict (key → scalar value).

    Returns:
        Flat env dict ready to be merged with the script builder's ``env``.
    """
    env: dict[str, str] = {}
    for key, value in inputs.items():
        str_val = str(value)
        env[key] = str_val
        upper_key = f"INPUT_{key.upper()}"
        if upper_key != key:
            env[upper_key] = str_val
    return env


def _upload_local_file_inputs(
    inputs: dict[str, Any],
    remote: Any,
    remote_work_dir: str,
    sep: str,
    *,
    is_windows: bool,
) -> dict[str, str]:
    """Upload local file-valued inputs to the remote work directory.

    For each input whose value is a string pointing to an existing local
    file, uploads that file to ``remote_work_dir`` and returns a mapping
    of the same env var keys to the *remote* file path.  Non-file inputs
    are passed through unchanged.

    Upload failures are treated as fatal: leaving a local path in cloud
    env vars is misleading and would fail later in less actionable ways.

    Args:
        inputs: Session inputs dict.
        remote: PostSSH/PostWinRM runner instance.
        remote_work_dir: Remote working directory path.
        sep: Path separator for the remote OS (``/`` or ``\\``).
        is_windows: Whether the remote is Windows.

    Returns:
        Dict of env var overrides with remote paths for file-valued keys.
    """
    overrides: dict[str, str] = {}
    for key, value in inputs.items():
        str_val = str(value)
        local = Path(str_val)
        if not local.is_file():
            continue
        remote_path = f"{remote_work_dir}{sep}{local.name}"
        try:
            remote.upload(str_val, remote_path)
            overrides[key] = remote_path
            overrides[f"INPUT_{key.upper()}"] = remote_path
            logger.debug("Uploaded session input file %s → %s", str_val, remote_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to upload session input file '{str_val}' "
                f"to '{remote_path}': {exc}"
            ) from exc
    return overrides


def _cleanup_remote(remote: Any) -> None:
    if hasattr(remote, "cleanup"):
        remote.cleanup()


def _build_tail_cmd(os_type: str, remote_log_file: str, lines: int) -> str:
    if os_type == "windows":
        return f'powershell "Get-Content -Tail {lines} {remote_log_file}"'
    return f"tail -{lines} {_shq(remote_log_file)} 2>/dev/null"


def _remote_join(os_type: str, base: str, *parts: str) -> str:
    sep = "\\" if os_type == "windows" else "/"
    path = base.rstrip("\\/")
    for part in parts:
        path = f"{path}{sep}{part.strip('\\/')}"
    return path


def _shq(value: str) -> str:
    """POSIX-shell quote helper for remote Linux commands."""
    return shlex.quote(str(value))


def _launch_remote_detached(
    remote: Any,
    *,
    is_windows: bool,
    session_id: str,
    remote_work_dir: str,
) -> tuple[int | None, str, str]:
    """Launch remote session script in detached mode and return pid/launcher/tmux."""
    if is_windows:
        start_cmd = (
            f'Start-Process powershell -ArgumentList "-File {remote_work_dir}\\run.ps1" '
            f"-WindowStyle Hidden -PassThru | Select-Object -ExpandProperty Id"
        )
        pid_output = remote.run(f'powershell "{start_cmd}"').strip()
        return _parse_pid(pid_output), "start-process", ""

    tmux_name = f"ofx-ses-{session_id}"
    has_tmux = (
        remote.run("command -v tmux >/dev/null 2>&1 && echo yes || echo no")
        .strip()
        .lower()
        == "yes"
    )
    if has_tmux:
        remote_run_script = f"{remote_work_dir}/run.sh"
        remote_out_log = f"{remote_work_dir}/output.log"
        tmux_cmd = f"bash {_shq(remote_run_script)} >> {_shq(remote_out_log)} 2>&1"
        remote.run(f"tmux new-session -d -s {_shq(tmux_name)} {_shq(tmux_cmd)}")
        pid_output = remote.run(
            f"tmux list-panes -t {_shq(tmux_name)} "
            "-F '#{pane_pid}' 2>/dev/null | head -n1"
        ).strip()
        return _parse_pid(pid_output), "tmux", tmux_name

    remote_run_script = f"{remote_work_dir}/run.sh"
    remote_out_log = f"{remote_work_dir}/output.log"
    pid_output = remote.run(
        f"nohup bash {_shq(remote_run_script)} > {_shq(remote_out_log)} 2>&1 & echo $!"
    ).strip()
    return _parse_pid(pid_output), "nohup", ""


def _parse_pid(pid_output: str) -> int | None:
    """Parse detached launcher PID output into an int."""
    try:
        return int(pid_output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def _remote_is_alive(remote: Any, session: Session) -> bool:
    """Check if remote detached session is still alive."""
    if session.os_type == "windows":
        check_cmd = (
            f'powershell "(Get-Process -Id {session.remote_pid} '
            f'-ErrorAction SilentlyContinue) -ne $null"'
        )
    elif session.remote_launcher == "tmux" and session.remote_tmux_session:
        check_cmd = (
            f"tmux has-session -t {_shq(session.remote_tmux_session)} 2>/dev/null "
            "&& echo alive || echo dead"
        )
    else:
        check_cmd = (
            f"kill -0 {session.remote_pid} 2>/dev/null && echo alive || echo dead"
        )
    output = remote.run(check_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip().lower()
    return "alive" in output or "true" in output


def _cancel_remote_execution(remote: Any, session: Session) -> None:
    """Cancel remote detached execution according to selected launcher."""
    if session.os_type == "windows":
        remote.run(
            f'powershell "Stop-Process -Id {session.remote_pid} -Force -ErrorAction SilentlyContinue"',
            timeout=_SSH_COMMAND_TIMEOUT,
        )
        return

    if session.remote_launcher == "tmux" and session.remote_tmux_session:
        remote.run(
            f"tmux kill-session -t {_shq(session.remote_tmux_session)} 2>/dev/null || true",
            timeout=_SSH_COMMAND_TIMEOUT,
        )
        return

    if session.remote_pid:
        remote.run(
            f"kill {session.remote_pid} 2>/dev/null; sleep 1; kill -9 {session.remote_pid} 2>/dev/null",
            timeout=_SSH_COMMAND_TIMEOUT,
        )


def _session_to_cloud_config(session: Session) -> Any:
    """Build a CloudConfig-like object from persisted session connection fields."""
    from ofx.models.cloud import CloudConfig

    os_type = session.os_type or "linux"
    connection_type = "winrm" if os_type == "windows" else "ssh"
    return CloudConfig(
        provider=session.cloud_provider or "static",
        os=os_type,  # type: ignore[arg-type]
        connection_type=connection_type,  # type: ignore[arg-type]
        ssh_user=session.ssh_user or "root",
        ssh_port=session.ssh_port or 22,
        ssh_key=session.ssh_key or "",
        ssh_password=session.ssh_password or "",
        winrm_user=session.winrm_user or session.ssh_user or "Administrator",
        winrm_password=session.ssh_password or "",
        winrm_ssl=session.winrm_ssl or False,
        winrm_port=session.winrm_port or (5986 if session.winrm_ssl else 5985),
        winrm_transport=session.winrm_transport or "ntlm",
    )


def _step_bundle_filename(step_index: int) -> str:
    """Deterministic bundle filename for Python-backed session steps."""
    return f".ofx_step_{step_index}.py"


def _build_step_bundle_source(step: Any) -> str:
    """Build bundled Python bootstrap source for `script`/`script_file` steps."""
    from ofx.cloud.script_runtime import (
        build_python_payload,
        resolve_python_step_source,
    )

    source = resolve_python_step_source(step)
    return build_python_payload(source, opsec_mode=True, obfuscate_sources=True)


class SessionManager:
    """High-level API for detached session lifecycle.

    Usage::

        mgr = SessionManager()
        session = await mgr.submit("scan.yml", target=SessionTarget.LOCAL)
        info = await mgr.status(session.id)
        await mgr.fetch(session.id, passphrase="s3cr3t")
    """

    def __init__(self, store: SessionStore | None = None):
        self.store = store or SessionStore()
        self._poll_failures: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Submit (fire-and-forget)
    # ------------------------------------------------------------------

    async def submit(
        self,
        workflow_file: str,
        *,
        job_id: str = "",
        target: SessionTarget = SessionTarget.LOCAL,
        cloud_profile: str = "",
        inputs: dict[str, Any] | None = None,
        name: str = "",
        env: dict[str, str] | None = None,
        tags: dict[str, str] | None = None,
        project: str = "",
    ) -> Session:
        """Submit a workflow as a detached session.

        Args:
            workflow_file: Workflow path or name.
            job_id: Specific job ID to run (empty = full workflow).
            target: LOCAL or CLOUD.
            cloud_profile: Cloud profile slug (for CLOUD target).
            inputs: Workflow inputs.
            name: Human-friendly session name.
            env: Extra environment variables.
            tags: Arbitrary tags.
            project: Project name to associate with this session.

        Returns:
            The created Session (status = RUNNING after this returns).
        """
        session_id = _secrets.token_hex(4)  # 8-char hex

        # Load workflow to extract job steps
        from ofx.settings import DEFAULT_WORKFLOWS_DIRS
        from ofx.utils.workflow_utils import find_workflow

        workflow = find_workflow(workflow_file, tuple(DEFAULT_WORKFLOWS_DIRS))
        session_steps, resolved_job_id = self._resolve_session_steps(workflow, job_id)
        workflow_name = workflow.name or Path(workflow_file).stem

        session = Session(
            id=session_id,
            name=name or workflow_name,
            workflow_file=workflow_file,
            job_id=resolved_job_id,
            target=target,
            status=SessionStatus.PROVISIONING,
            cloud_profile=cloud_profile,
            inputs=inputs or {},
            tags=tags or {},
            project=project,
        )

        # Save initial state
        self.store.save(session)

        if target == SessionTarget.LOCAL:
            session = await self._submit_local(
                session,
                session_steps,
                env or {},
                workflow_name=workflow_name,
            )
        else:
            session = await self._submit_cloud(
                session,
                session_steps,
                env or {},
                cloud_profile,
                workflow_name=workflow_name,
            )

        return session

    def _save_session(self, session: Session, update: dict) -> Session:
        """Update session fields and persist to store."""
        session = session.model_copy(update=update)
        self.store.save(session)
        return session

    # ------------------------------------------------------------------
    # Local submission
    # ------------------------------------------------------------------

    async def _submit_local(
        self,
        session: Session,
        steps: list[Any],
        env: dict[str, str],
        *,
        workflow_name: str,
    ) -> Session:
        """Start workflow steps as a detached local background process."""
        session_dir = self.store.session_dir(session.id)
        work_dir = session_dir / "workspace"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir = work_dir / "output"
        output_dir.mkdir(exist_ok=True)

        at_rest_key = _secrets.token_hex(32)
        key_file = work_dir / ".skey"
        key_file.write_text(at_rest_key)
        key_file.chmod(0o600)

        # Inject session inputs as env vars; copy local files into workspace
        input_env = _inputs_to_env(session.inputs)
        for key, value in session.inputs.items():
            local = Path(str(value))
            if local.is_file():
                dest = work_dir / local.name
                try:
                    shutil.copy2(str(local), str(dest))
                    dest_str = str(dest)
                    input_env[key] = dest_str
                    input_env[f"INPUT_{key.upper()}"] = dest_str
                    logger.debug("Staged session input file %s → %s", local, dest)
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to stage session input file '{local}': {exc}"
                    ) from exc
        merged_env = {**input_env, **env}  # explicit env takes precedence

        script_content = build_session_script(
            steps,
            session_id=session.id,
            work_dir=str(work_dir),
            workflow_name=workflow_name,
            job_name=session.job_id,
            env=merged_env,
            os_type="linux",
            encrypt_at_rest=True,
        )

        script_path = work_dir / "run.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o700)

        log_file_path = work_dir / "output.log"
        self._stage_script_files(steps, work_dir)
        work_dir.chmod(0o700)

        session = session.model_copy(
            update={
                "status": SessionStatus.RUNNING,
                "remote_work_dir": str(work_dir),
                "remote_log_file": str(log_file_path),
                "output_path": str(session_dir),
                "os_type": "linux",
                "at_rest_key": at_rest_key,
                "at_rest_encrypted": True,
            }
        )

        proc = subprocess.Popen(
            ["bash", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(work_dir),
            env={**os.environ, "SESSION_ID": session.id, **merged_env},
        )

        session = self._save_session(session, {"remote_pid": proc.pid})
        logger.info("Local session %s started (PID %d)", session.id, proc.pid)
        return session

    # ------------------------------------------------------------------
    # Cloud submission
    # ------------------------------------------------------------------

    async def _submit_cloud(
        self,
        session: Session,
        steps: list[Any],
        env: dict[str, str],
        cloud_profile: str,
        *,
        workflow_name: str,
    ) -> Session:
        """Provision a VPS, upload the script, and start detached via SSH/WinRM."""
        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.config import get_cloud_profile_manager
        from ofx.cloud.ssh import wait_for_connectivity
        from ofx.models.cloud import CloudConfig

        # Resolve cloud config from profile
        mgr = get_cloud_profile_manager()
        cfg = CloudConfig(profile=cloud_profile) if cloud_profile else CloudConfig()
        resolved = mgr.resolve(cfg)

        os_type = getattr(resolved, "os", "linux") or "linux"
        is_windows = os_type == "windows"

        session = self._save_session(
            session,
            {
                "cloud_provider": resolved.provider or "static",
                "auto_destroy": bool(getattr(resolved, "auto_destroy", True)),
                "os_type": os_type,
                "ssh_user": resolved.ssh_user or "root",
                "ssh_port": resolved.ssh_port or 22,
                "ssh_key": resolved.ssh_key or "",
                "ssh_password": resolved.ssh_password or "",
                "winrm_port": resolved.winrm_port
                or (5986 if resolved.winrm_ssl else 5985),
                "winrm_ssl": resolved.winrm_ssl or False,
                "winrm_transport": resolved.winrm_transport or "ntlm",
                "winrm_user": resolved.winrm_user or "Administrator",
            },
        )

        # Provision
        provider_name = resolved.provider or "static"
        from ofx.cloud.runtime import build_provider_kwargs, create_remote_runner

        provider_kwargs = build_provider_kwargs(resolved)
        provider = CloudProviderRegistry.create(provider_name, **provider_kwargs)

        instance = await provider.create_instance(resolved)

        try:
            if provider_name != "static":
                instance = await provider.wait_until_ready(
                    instance.instance_id, timeout=resolved.startup_timeout or 300
                )
                refreshed = await provider.get_instance(instance.instance_id)
                if refreshed and refreshed.ip:
                    instance = refreshed

            if not instance or not instance.ip:
                raise RuntimeError("Instance has no IP address")
        except Exception:
            if provider_name != "static" and instance and instance.instance_id:
                try:
                    await provider.destroy_instance(instance.instance_id)
                except Exception as destroy_err:
                    logger.warning(
                        "Failed to destroy orphaned instance %s: %s",
                        instance.instance_id,
                        destroy_err,
                    )
            error_msg = str(instance) if instance else "Instance creation failed"
            session = self._save_session(
                session, {"status": SessionStatus.FAILED, "error": error_msg}
            )
            raise

        session = self._save_session(
            session, {"instance_id": instance.instance_id, "instance_ip": instance.ip}
        )

        from ofx.cloud.ssh import wait_for_login

        await wait_for_connectivity(
            host=instance.ip,
            os_type="windows" if is_windows else "linux",
            ssh_port=resolved.ssh_port or 22,
            winrm_port=resolved.winrm_port or (5986 if resolved.winrm_ssl else 5985),
            timeout=180,
        )
        await wait_for_login(
            host=instance.ip,
            cfg=resolved,
            timeout=getattr(resolved, "login_timeout", 300) or 300,
        )

        # Build script — inputs injected as env vars; file paths updated after upload
        sep = "\\" if is_windows else "/"
        remote_work_dir = (
            f"C:\\Windows\\Temp\\.ses-{session.id}"
            if is_windows
            else f"/tmp/.ses-{session.id}"
        )

        at_rest_key = _secrets.token_hex(32)

        # Base input env (file paths still point to local files at this stage)
        input_env = _inputs_to_env(session.inputs)
        merged_env = {**input_env, **env}  # explicit env takes precedence

        script_content = build_session_script(
            steps,
            session_id=session.id,
            work_dir=remote_work_dir,
            workflow_name=workflow_name,
            job_name=session.job_id,
            env=merged_env,
            os_type=os_type,
            encrypt_at_rest=True,
        )
        session = session.model_copy(
            update={"at_rest_key": at_rest_key, "at_rest_encrypted": True}
        )

        remote = create_remote_runner(resolved, instance.ip, max_retries=3)
        try:
            # Upload
            session = self._save_session(session, {"status": SessionStatus.UPLOADING})

            if is_windows:
                remote.run(f'mkdir "{remote_work_dir}" 2>nul')
            else:
                remote.run(f"mkdir -p {remote_work_dir} && chmod 700 {remote_work_dir}")

            # Upload local file-valued inputs and get remote path overrides
            file_overrides = _upload_local_file_inputs(
                session.inputs, remote, remote_work_dir, sep, is_windows=is_windows
            )
            if file_overrides:
                # Rebuild script with corrected remote paths
                merged_env.update(file_overrides)
                script_content = build_session_script(
                    steps,
                    session_id=session.id,
                    work_dir=remote_work_dir,
                    workflow_name=workflow_name,
                    job_name=session.job_id,
                    env=merged_env,
                    os_type=os_type,
                    encrypt_at_rest=True,
                )

            # Upload key and script via temp files
            _upload_temp_content(
                remote, at_rest_key, f"{remote_work_dir}{sep}.skey", suffix=".key"
            )
            ext = ".ps1" if is_windows else ".sh"
            _upload_temp_content(
                remote, script_content, f"{remote_work_dir}{sep}run{ext}", suffix=ext
            )

            if is_windows:
                remote.run(
                    f"powershell \"icacls '{remote_work_dir}' /inheritance:r "
                    f"/grant:r '$env:USERNAME:(OI)(CI)F' /T 2>$null\"",
                )
            else:
                remote.run(f"chmod 600 {remote_work_dir}/.skey")
                remote.run(f"chmod 700 {remote_work_dir}/run.sh")

            self._upload_script_files(
                steps, remote, remote_work_dir, is_windows=is_windows
            )

            # Start detached
            pid, launcher, tmux_name = _launch_remote_detached(
                remote,
                is_windows=is_windows,
                session_id=session.id,
                remote_work_dir=remote_work_dir,
            )

            remote_log = f"{remote_work_dir}{sep}output.log"
            session = self._save_session(
                session,
                {
                    "status": SessionStatus.RUNNING,
                    "remote_pid": pid,
                    "remote_work_dir": remote_work_dir,
                    "remote_log_file": remote_log,
                    "remote_tmux_session": tmux_name,
                    "remote_launcher": launcher,
                    "output_path": str(self.store.session_dir(session.id)),
                },
            )
            logger.info(
                "Cloud session %s started on %s (PID %s)", session.id, instance.ip, pid
            )
        finally:
            _cleanup_remote(remote)

        return session

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self, session_id: str) -> Session:
        """Check the current status of a session.

        For running sessions, probes the remote/local PID and log markers.
        """
        session = self.store.load(session_id)

        if not session.is_running():
            return session

        if session.target == SessionTarget.LOCAL:
            session = self._check_local_status(session)
        else:
            session = await self._check_cloud_status(session)

        self.store.save(session)
        return session

    def _check_local_status(self, session: Session) -> Session:
        """Check if a local background process is still alive."""
        if session.remote_pid is None:
            return session.model_copy(
                update={
                    "status": SessionStatus.FAILED,
                    "error": "No PID recorded",
                    "finished_at": datetime.now(UTC),
                }
            )

        alive = _pid_alive(session.remote_pid)

        if alive:
            # Check log for markers (may have finished just now)
            marker = _read_log_marker(Path(session.remote_log_file))
            if marker == _DONE_MARKER:
                return session.model_copy(
                    update={
                        "status": SessionStatus.COMPLETED,
                        "finished_at": datetime.now(UTC),
                    }
                )
            if marker == _FAIL_MARKER:
                return session.model_copy(
                    update={
                        "status": SessionStatus.FAILED,
                        "finished_at": datetime.now(UTC),
                    }
                )
            return session  # Still running

        # Process exited — check log to determine outcome
        marker = _read_log_marker(Path(session.remote_log_file))
        if marker == _DONE_MARKER:
            return session.model_copy(
                update={
                    "status": SessionStatus.COMPLETED,
                    "finished_at": datetime.now(UTC),
                }
            )
        return session.model_copy(
            update={
                "status": SessionStatus.FAILED,
                "error": "Process exited without success marker",
                "finished_at": datetime.now(UTC),
            }
        )

    async def _check_cloud_status(self, session: Session) -> Session:
        """SSH in and check PID + log markers on a cloud VPS.

        Tracks consecutive connection failures per session.  After
        *_MAX_CONSECUTIVE_FAILURES* the session is marked ``UNREACHABLE``.
        On a successful probe the failure counter resets to zero.
        """
        failures = getattr(self, "_poll_failures", {})
        if not hasattr(self, "_poll_failures"):
            self._poll_failures = failures

        if session.remote_pid is None:
            # No PID recorded — check log only
            try:
                remote = self._reconnect(session)
                try:
                    tail_cmd = _build_tail_cmd(
                        session.os_type, session.remote_log_file, 5
                    )
                    log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
                    marker = _parse_marker(log_tail)

                    self._poll_failures[session.id] = 0

                    if marker == _DONE_MARKER:
                        return session.model_copy(
                            update={
                                "status": SessionStatus.COMPLETED,
                                "finished_at": datetime.now(UTC),
                            }
                        )
                    if marker == _FAIL_MARKER:
                        return session.model_copy(
                            update={
                                "status": SessionStatus.FAILED,
                                "finished_at": datetime.now(UTC),
                            }
                        )

                    if (
                        session.os_type != "windows"
                        and session.remote_launcher == "tmux"
                        and session.remote_tmux_session
                    ):
                        tmux_alive = (
                            remote.run(
                                f"tmux has-session -t {_shq(session.remote_tmux_session)} "
                                "2>/dev/null && echo alive || echo dead",
                                timeout=_SSH_COMMAND_TIMEOUT,
                            )
                            .strip()
                            .lower()
                        )
                        if "alive" in tmux_alive:
                            return session
                finally:
                    _cleanup_remote(remote)
            except Exception as exc:
                count = self._poll_failures.get(session.id, 0) + 1
                self._poll_failures[session.id] = count
                backoff = min(
                    _INITIAL_POLL_INTERVAL * (_POLL_BACKOFF_FACTOR ** count),
                    _MAX_POLL_INTERVAL,
                )
                if count >= _MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        "Session %s unreachable after %d consecutive failures",
                        session.id,
                        count,
                    )
                    return session.model_copy(
                        update={
                            "status": SessionStatus.UNREACHABLE,
                            "error": f"Unreachable after {count} consecutive poll failures: {exc}",
                        }
                    )
                logger.debug(
                    "Status check (no-pid) failed for %s (attempt %d, next backoff %.1fs): %s",
                    session.id,
                    count,
                    backoff,
                    exc,
                )
            return session

        try:
            remote = self._reconnect(session)
        except Exception as exc:
            count = self._poll_failures.get(session.id, 0) + 1
            self._poll_failures[session.id] = count
            backoff = min(
                _INITIAL_POLL_INTERVAL * (_POLL_BACKOFF_FACTOR ** count),
                _MAX_POLL_INTERVAL,
            )
            if count >= _MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Session %s unreachable after %d consecutive failures",
                    session.id,
                    count,
                )
                return session.model_copy(
                    update={
                        "status": SessionStatus.UNREACHABLE,
                        "error": f"Unreachable after {count} consecutive poll failures: {exc}",
                    }
                )
            logger.debug(
                "Cannot reconnect to %s (attempt %d, next backoff %.1fs): %s",
                session.instance_ip,
                count,
                backoff,
                exc,
            )
            return session  # Can't determine — leave as-is

        try:
            alive = _remote_is_alive(remote, session)

            # Check log marker
            tail_cmd = _build_tail_cmd(session.os_type, session.remote_log_file, 5)
            log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
            marker = _parse_marker(log_tail)

            self._poll_failures[session.id] = 0

            if marker == _DONE_MARKER:
                return session.model_copy(
                    update={
                        "status": SessionStatus.COMPLETED,
                        "finished_at": datetime.now(UTC),
                    }
                )
            if marker == _FAIL_MARKER or (not alive and marker is None):
                return session.model_copy(
                    update={
                        "status": SessionStatus.FAILED,
                        "error": "Process exited without success marker"
                        if not marker
                        else "",
                        "finished_at": datetime.now(UTC),
                    }
                )

            return session  # Still running
        except Exception as exc:
            count = self._poll_failures.get(session.id, 0) + 1
            self._poll_failures[session.id] = count
            backoff = min(
                _INITIAL_POLL_INTERVAL * (_POLL_BACKOFF_FACTOR ** count),
                _MAX_POLL_INTERVAL,
            )
            if count >= _MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "Session %s unreachable after %d consecutive failures",
                    session.id,
                    count,
                )
                return session.model_copy(
                    update={
                        "status": SessionStatus.UNREACHABLE,
                        "error": f"Unreachable after {count} consecutive poll failures: {exc}",
                    }
                )
            logger.debug(
                "Status check failed for %s (attempt %d, next backoff %.1fs): %s",
                session.id,
                count,
                backoff,
                exc,
            )
            return session
        finally:
            _cleanup_remote(remote)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    async def logs(self, session_id: str, tail: int = 50, follow: bool = False) -> str:
        """Retrieve log output from a session.

        Args:
            session_id: Session ID.
            tail: Number of lines to return.
            follow: If True, streams (blocks) — only for local sessions.

        Returns:
            Log content as a string.
        """
        session = self.store.load(session_id)

        if session.target == SessionTarget.LOCAL:
            log_path = Path(session.remote_log_file)
            if not log_path.exists():
                return "(no log file yet)"
            if follow:
                # Return last N lines; real follow would need streaming
                return _tail_file(log_path, tail)
            return _tail_file(log_path, tail)

        try:
            remote = self._reconnect(session)
            try:
                cmd = _build_tail_cmd(session.os_type, session.remote_log_file, tail)
                output = remote.run(cmd, timeout=30)
            finally:
                _cleanup_remote(remote)
            return output
        except Exception as exc:
            return f"(cannot retrieve logs: {exc})"

    # ------------------------------------------------------------------
    # Fetch results
    # ------------------------------------------------------------------

    async def fetch(
        self,
        session_id: str,
        *,
        passphrase: str = "",
        output_dir: Path | None = None,
    ) -> Path:
        """Download results from a completed session.

        If the session has at-rest encryption enabled, the encrypted archive
        is downloaded and transparently decrypted using the stored key before
        results are written to disk.

        Args:
            session_id: Session ID.
            passphrase: If provided, re-encrypt results with this passphrase
                after fetching (user-level encryption).
            output_dir: Override destination directory.

        Returns:
            Path to the results directory (or encrypted file).
        """
        session = await self.status(session_id)  # Refresh status

        if session.is_running():
            raise RuntimeError(
                f"Session {session_id} is still running (status={session.status.value}). "
                "Wait for completion or cancel first."
            )

        results = output_dir or self._resolve_results_dir(session)

        if session.target == SessionTarget.LOCAL:
            self._fetch_local_results(session, results)
        else:
            # Cloud — download via SCP
            await self._fetch_cloud_results(session, results)
            session = await self._auto_destroy_after_fetch(session)

        # Re-encrypt with user passphrase if requested
        if passphrase:
            enc_path = encrypt_results(results, passphrase)
            session = self._save_session(
                session,
                {
                    "status": SessionStatus.ENCRYPTED,
                    "encrypted": True,
                    "encrypted_file": str(enc_path),
                    "results_path": str(results),
                },
            )
        else:
            session = self._save_session(
                session,
                {
                    "status": SessionStatus.FETCHED,
                    "results_path": str(results),
                },
            )

        return results if not passphrase else Path(session.encrypted_file)

    async def _auto_destroy_after_fetch(self, session: Session) -> Session:
        """Auto-destroy cloud instance after fetch when configured and non-static."""
        if session.target != SessionTarget.CLOUD:
            return session
        if not session.instance_id:
            return session
        if not session.auto_destroy:
            return session
        if (session.cloud_provider or "static") == "static":
            return session

        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.config import get_cloud_profile_manager
        from ofx.models.cloud import CloudConfig

        try:
            cfg = (
                CloudConfig(profile=session.cloud_profile)
                if session.cloud_profile
                else CloudConfig()
            )
            mgr = get_cloud_profile_manager()
            resolved = mgr.resolve(cfg)
            from ofx.cloud.runtime import build_provider_kwargs

            provider_kwargs = build_provider_kwargs(resolved)
            provider = CloudProviderRegistry.create(
                session.cloud_provider or resolved.provider or "static",
                **provider_kwargs,
            )
            await provider.destroy_instance(session.instance_id)
            return self._save_session(
                session,
                {
                    "instance_id": "",
                    "instance_ip": "",
                },
            )
        except Exception as exc:
            logger.warning(
                "Auto-destroy after fetch failed for session %s (instance %s): %s",
                session.id,
                session.instance_id,
                exc,
            )
            return session

    def _fetch_local_results(self, session: Session, results: Path) -> None:
        """Copy local session output to results dir, decrypting if needed."""
        work_dir = Path(session.remote_work_dir)
        results.mkdir(parents=True, exist_ok=True)

        enc_file = work_dir / "output.enc"
        if session.at_rest_encrypted and enc_file.exists():
            # Decrypt the at-rest archive
            _decrypt_at_rest_openssl(enc_file, session.at_rest_key, results)
        else:
            # Unencrypted fallback — copy output/ contents
            work_output = work_dir / "output"
            if work_output.exists():
                for item in work_output.iterdir():
                    dest = results / item.name
                    if item.is_file():
                        shutil.copy2(str(item), str(dest))
                    elif item.is_dir():
                        shutil.copytree(str(item), str(dest), dirs_exist_ok=True)

        # Also copy the log
        log_path = Path(session.remote_log_file)
        if log_path.exists():
            shutil.copy2(str(log_path), str(results / "output.log"))

    async def _fetch_cloud_results(self, session: Session, results: Path) -> None:
        """Download output from a cloud VPS via SCP, decrypting if needed."""
        remote = self._reconnect(session)
        try:
            results.mkdir(parents=True, exist_ok=True)

            if session.at_rest_encrypted:
                # Download the encrypted archive
                enc_remote = _remote_join(
                    session.os_type, session.remote_work_dir, "output.enc"
                )

                local_enc = results.parent / f"output_{session.id}.enc"
                try:
                    remote.download(enc_remote, str(local_enc))
                except Exception as exc:
                    logger.warning(
                        "Encrypted archive not found on VPS (%s); "
                        "falling back to unencrypted fetch",
                        exc,
                    )
                    # Fall through to unencrypted fetch below
                    local_enc = None  # type: ignore[assignment]

                if local_enc and local_enc.exists():
                    _decrypt_at_rest_openssl(local_enc, session.at_rest_key, results)
                    local_enc.unlink(missing_ok=True)
                    # Also grab the log (not encrypted)
                    try:
                        remote.download(
                            session.remote_log_file, str(results / "output.log")
                        )
                    except Exception as e:
                        logger.debug("Failed to download remote log: %s", e)
                    return

            # Unencrypted fallback — download individual files
            if session.os_type == "windows":
                files_cmd = (
                    f"powershell \"Get-ChildItem -Path '{session.remote_work_dir}\\output' "
                    f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
                )
            else:
                files_cmd = f"ls -1 {session.remote_work_dir}/output 2>/dev/null"

            output = remote.run(files_cmd, timeout=30)
            files = [f.strip() for f in output.strip().split("\n") if f.strip()]

            for fname in files:
                rpath = _remote_join(
                    session.os_type, session.remote_work_dir, "output", fname
                )
                try:
                    remote.download(rpath, str(results / fname))
                except Exception as exc:
                    logger.debug("Failed to download %s: %s", rpath, exc)

            # Also grab the log
            try:
                remote.download(session.remote_log_file, str(results / "output.log"))
            except Exception as e:
                logger.debug("Failed to download remote log: %s", e)
        finally:
            _cleanup_remote(remote)

    # ------------------------------------------------------------------
    # Decrypt
    # ------------------------------------------------------------------

    async def decrypt(
        self,
        session_id: str,
        passphrase: str,
        output_dir: Path | None = None,
    ) -> Path:
        """Decrypt previously encrypted session results.

        Returns:
            Path to the decrypted results directory.
        """
        session = self.store.load(session_id)
        if not session.encrypted or not session.encrypted_file:
            raise RuntimeError(f"Session {session_id} results are not encrypted")

        enc_path = Path(session.encrypted_file)
        out = output_dir or self.store.results_dir(session_id) / "decrypted"
        result = decrypt_results(enc_path, passphrase, out)
        return result

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel(self, session_id: str) -> Session:
        """Kill the running process and mark session as canceled."""
        session = self.store.load(session_id)

        if not session.is_running():
            return session

        if session.target == SessionTarget.LOCAL:
            if session.remote_pid:
                try:
                    os.killpg(os.getpgid(session.remote_pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    try:
                        os.kill(session.remote_pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        pass
        else:
            # SSH in and kill
            try:
                remote = self._reconnect(session)
                try:
                    _cancel_remote_execution(remote, session)
                finally:
                    _cleanup_remote(remote)
            except Exception as exc:
                logger.debug("Cancel failed for %s: %s", session_id, exc)

        return self._save_session(
            session,
            {
                "status": SessionStatus.CANCELED,
                "finished_at": datetime.now(UTC),
            },
        )

    # ------------------------------------------------------------------
    # Destroy (tear down VPS)
    # ------------------------------------------------------------------

    async def destroy(self, session_id: str, force: bool = False) -> Session:
        """Destroy the VPS for a cloud session. Cancel first if still running.

        For local sessions, just cleans up the workspace.
        """
        session = self.store.load(session_id)

        if session.is_running():
            if force:
                session = await self.cancel(session_id)
            else:
                raise RuntimeError(
                    f"Session {session_id} is still running. Use --force to cancel and destroy."
                )

        if session.target == SessionTarget.CLOUD and session.instance_id:
            from ofx.cloud import CloudProviderRegistry
            from ofx.cloud.config import get_cloud_profile_manager
            from ofx.models.cloud import CloudConfig

            try:
                cfg = (
                    CloudConfig(profile=session.cloud_profile)
                    if session.cloud_profile
                    else CloudConfig()
                )
                mgr = get_cloud_profile_manager()
                resolved = mgr.resolve(cfg)
                from ofx.cloud.runtime import build_provider_kwargs

                provider_kwargs = build_provider_kwargs(resolved)
                provider = CloudProviderRegistry.create(
                    session.cloud_provider or resolved.provider or "static",
                    **provider_kwargs,
                )
                await provider.destroy_instance(session.instance_id)
            except Exception as exc:
                logger.warning(
                    "Failed to destroy instance %s: %s", session.instance_id, exc
                )

        return self._save_session(
            session,
            {
                "status": SessionStatus.DESTROYED,
                "finished_at": session.finished_at or datetime.now(UTC),
            },
        )

    async def bundle_artifacts(
        self,
        session_id: str,
        *,
        output_file: Path | None = None,
        include_project_context: bool = True,
    ) -> Path:
        """Create a tar.gz bundle with session metadata + fetched artifacts."""
        session = self.store.load(session_id)
        session_dir = self.store.session_dir(session_id)
        results_dir = Path(session.results_path) if session.results_path else None
        if results_dir is None or not results_dir.exists():
            # Attempt fetch for completed sessions if results were not fetched yet.
            if session.status in (
                SessionStatus.COMPLETED,
                SessionStatus.FETCHED,
                SessionStatus.ENCRYPTED,
            ):
                await self.fetch(session_id)
                session = self.store.load(session_id)
                results_dir = (
                    Path(session.results_path) if session.results_path else None
                )
            if results_dir is None or not results_dir.exists():
                raise RuntimeError(
                    f"No fetched results available for session {session_id}. "
                    "Run 'ofx session fetch <id>' first."
                )

        bundle_path = output_file or (session_dir / f"bundle_{session_id}.tar.gz")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = {
            "session_id": session.id,
            "name": session.name,
            "status": session.status.value,
            "target": session.target.value,
            "workflow_file": session.workflow_file,
            "job_id": session.job_id,
            "execution_scope": session.job_id or "full-workflow",
            "project": session.project,
            "started_at": session.started_at.isoformat(),
            "finished_at": session.finished_at.isoformat()
            if session.finished_at
            else None,
            "instance_ip": session.instance_ip,
            "instance_id": session.instance_id,
            "cloud_profile": session.cloud_profile,
            "fleet_group_id": session.fleet_group_id,
            "fleet_index": session.fleet_index,
            "fleet_total": session.fleet_total,
        }

        manifest_path = session_dir / f"bundle_manifest_{session_id}.json"
        manifest_path.write_text(__import__("json").dumps(manifest, indent=2))
        try:
            with tarfile.open(bundle_path, "w:gz") as tf:
                tf.add(manifest_path, arcname="manifest.json")
                tf.add(session_dir / "session.json", arcname="session.json")
                if results_dir.exists():
                    tf.add(results_dir, arcname="results")
                if include_project_context and session.project:
                    try:
                        from ofx.commands.project.project_manager import ProjectManager

                        project_path = Path(
                            ProjectManager.resolve_path(session.project)
                        )
                        if project_path.exists():
                            tf.add(project_path / "logs", arcname="project_logs")
                    except Exception as e:
                        logger.debug("Failed to add project logs to bundle: %s", e)
        finally:
            manifest_path.unlink(missing_ok=True)

        return bundle_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_results_dir(self, session: Session) -> Path:
        """Resolve where to store fetched results.

        If the session is associated with a project, results go into
        ``<project_path>/evidence/sessions/<session_id>/``.
        Otherwise falls back to ``~/.ofx/sessions/<id>/results/``.
        """
        if session.project:
            try:
                from ofx.commands.project.project_manager import ProjectManager

                project_path = Path(ProjectManager.resolve_path(session.project))
                if project_path.exists():
                    dest = project_path / "evidence" / "sessions" / session.id
                    dest.mkdir(parents=True, exist_ok=True)
                    return dest
            except Exception as e:
                logger.debug("Project evidence path resolution failed: %s", e)
        return self.store.results_dir(session.id)

    def _resolve_session_steps(
        self, workflow: Any, job_id: str
    ) -> tuple[list[Any], str]:
        """Resolve steps to execute for a session.

        When ``job_id`` is provided, only that job's steps are used.
        Otherwise, all workflow jobs are linearized by dependency stage order.
        """
        jobs = workflow.jobs
        if not isinstance(jobs, dict):
            raise ValueError("Workflow jobs must be a mapping of job_id -> job")
        if not jobs:
            raise ValueError("Workflow has no jobs")

        if job_id:
            job = jobs.get(job_id)
            if job is None:
                raise ValueError(f"Job '{job_id}' not found in workflow")
            return list(job.steps), job.jid

        from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

        schedule = WorkflowScheduler(jobs).plan().schedule
        selected_steps: list[Any] = []
        for stage in schedule:
            for staged_job_id in stage:
                job = jobs[staged_job_id]
                for idx, step in enumerate(job.steps):
                    base_name = step.name or f"step_{idx}"
                    selected_steps.append(
                        step.model_copy(update={"name": f"{job.jid}::{base_name}"})
                    )
        return selected_steps, ""

    def _reconnect(self, session: Session) -> Any:
        """Create a PostSSH or PostWinRM to reconnect to a session's host."""
        from ofx.cloud.runtime import create_remote_runner

        cfg = _session_to_cloud_config(session)
        return create_remote_runner(cfg, session.instance_ip, max_retries=2)

    def _stage_script_files(self, steps: list, work_dir: Path) -> None:
        """Stage bundled Python step artifacts into the local workspace."""
        from ofx.models.step import RunType

        for idx, step in enumerate(steps):
            if step.get_run_type() not in (RunType.SCRIPT, RunType.SCRIPT_FILE):
                continue
            dest = work_dir / _step_bundle_filename(idx)
            dest.write_text(_build_step_bundle_source(step))
            dest.chmod(0o600)

    def _upload_script_files(
        self, steps: list, remote: Any, remote_work_dir: str, *, is_windows: bool
    ) -> None:
        """Upload bundled Python step artifacts to the remote host."""
        from ofx.models.step import RunType

        for idx, step in enumerate(steps):
            if step.get_run_type() not in (RunType.SCRIPT, RunType.SCRIPT_FILE):
                continue
            bundle_source = _build_step_bundle_source(step)
            filename = _step_bundle_filename(idx)
            remote_path = (
                f"{remote_work_dir}\\{filename}"
                if is_windows
                else f"{remote_work_dir}/{filename}"
            )
            fd, local_path = tempfile.mkstemp(prefix=".ofx_step_", suffix=".py")
            os.close(fd)
            Path(local_path).write_text(bundle_source)
            os.chmod(local_path, 0o600)
            try:
                remote.upload(local_path, remote_path)
            finally:
                Path(local_path).unlink(missing_ok=True)


# ======================================================================
# Module-level helpers
# ======================================================================


def _upload_temp_content(
    remote: Any, content: str, remote_path: str, *, suffix: str = ""
) -> None:
    """Write content to a temp file, upload it, then clean up."""
    fd, local_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(local_path).write_text(content)
    os.chmod(local_path, 0o600)
    try:
        remote.upload(local_path, remote_path)
    finally:
        Path(local_path).unlink(missing_ok=True)


def _decrypt_at_rest_openssl(
    enc_file: Path, at_rest_key: str, output_dir: Path
) -> None:
    """Decrypt an at-rest encrypted archive produced by the session script.

    The session script uses ``openssl enc -aes-256-cbc -pbkdf2`` with the
    key written to a file.  We replicate the same decryption locally.

    Args:
        enc_file: Path to the ``output.enc`` file.
        at_rest_key: The hex key string used for encryption.
        output_dir: Where to extract the decrypted tar.gz contents.
    """
    import tarfile as _tarfile

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write key to a temp file for openssl
    key_path = enc_file.parent / f".dec_{_secrets.token_hex(4)}"
    key_path.write_text(at_rest_key)
    key_path.chmod(0o600)

    tar_path = enc_file.parent / "output_dec.tar.gz"

    try:
        result = subprocess.run(
            [
                "openssl",
                "enc",
                "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-iter",
                "100000",
                "-pass",
                f"file:{key_path}",
                "-in",
                str(enc_file),
                "-out",
                str(tar_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"openssl decryption failed (rc={result.returncode}): {result.stderr.strip()}"
            )

        # Extract the tar into output_dir
        with _tarfile.open(str(tar_path), "r:gz") as tar:
            # Strip the leading "output/" prefix so files land directly in output_dir
            for member in tar.getmembers():
                # e.g. "output/scan.txt" → "scan.txt"
                parts = Path(member.name).parts
                if parts and len(parts) > 1 and parts[0] == "output":
                    member.name = str(Path(*parts[1:]))
                elif parts and parts[0] == "output":
                    continue  # skip the bare directory entry
                tar.extract(member, path=str(output_dir), filter="data")

        logger.debug("At-rest decrypted %s → %s", enc_file, output_dir)
    finally:
        key_path.unlink(missing_ok=True)
        tar_path.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    """Check whether a local PID is still running (not a zombie)."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    # os.kill(pid, 0) succeeds for zombie processes too.  Check /proc
    # to distinguish zombies from genuinely alive processes.
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("State:"):
                    return "Z" not in line  # 'Z (zombie)'
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return True


def _read_log_marker(path: Path) -> str | None:
    """Read the last few lines of a log and return the status marker."""
    if not path.exists():
        return None
    try:
        text = path.read_text(errors="replace")
        return _parse_marker(text)
    except Exception as e:
        logger.debug("Failed to read status file %s: %s", path, e)
        return None


def _parse_marker(text: str) -> str | None:
    """Find __TASK_OK__ or __TASK_ERR__ in text."""
    if _DONE_MARKER in text:
        return _DONE_MARKER
    if _FAIL_MARKER in text:
        return _FAIL_MARKER
    return None


def _tail_file(path: Path, n: int = 50) -> str:
    """Return the last N lines of a file."""
    try:
        lines = path.read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return "(cannot read log)"
