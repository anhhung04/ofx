"""Session lifecycle manager — submit, status, fetch, cancel, destroy.

Orchestrates both **local** (background subprocess) and **cloud** (VPS) sessions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets as _secrets
import shutil
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.encryption import decrypt_results, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.store import SessionStore

logger = logging.getLogger("ofx")

# Marker strings the script builder appends on completion/failure
_DONE_MARKER = "__OFX_DONE__"
_FAIL_MARKER = "__OFX_FAIL__"


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
    ) -> Session:
        """Submit a workflow as a detached session.

        Args:
            workflow_file: Workflow path or name.
            job_id: Specific job ID to run (empty = first job).
            target: LOCAL or CLOUD.
            cloud_profile: Cloud profile slug (for CLOUD target).
            inputs: Workflow inputs.
            name: Human-friendly session name.
            env: Extra environment variables.
            tags: Arbitrary tags.

        Returns:
            The created Session (status = RUNNING after this returns).
        """
        session_id = _secrets.token_hex(4)  # 8-char hex

        # Load workflow to extract job steps
        from ofx.settings import DEFAULT_WORKFLOWS_DIRS
        from ofx.utils.workflow_utils import find_workflow

        workflow = find_workflow(
            workflow_file, tuple(DEFAULT_WORKFLOWS_DIRS)
        )
        job = self._resolve_job(workflow, job_id)

        session = Session(
            id=session_id,
            name=name or job.name or workflow.name or Path(workflow_file).stem,
            workflow_file=workflow_file,
            job_id=job.jid,
            target=target,
            status=SessionStatus.PROVISIONING,
            cloud_profile=cloud_profile,
            inputs=inputs or {},
            tags=tags or {},
        )

        # Save initial state
        self.store.save(session)

        if target == SessionTarget.LOCAL:
            session = await self._submit_local(session, job, env or {})
        else:
            session = await self._submit_cloud(session, job, env or {}, cloud_profile)

        return session

    # ------------------------------------------------------------------
    # Local submission
    # ------------------------------------------------------------------

    async def _submit_local(
        self,
        session: Session,
        job: Any,
        env: dict[str, str],
    ) -> Session:
        """Start workflow steps as a detached local background process."""
        session_dir = self.store.session_dir(session.id)
        work_dir = session_dir / "workspace"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir = work_dir / "output"
        output_dir.mkdir(exist_ok=True)

        # Generate at-rest encryption key and write key file
        at_rest_key = _secrets.token_hex(32)  # 64-char hex → 256-bit
        key_file = work_dir / ".ofx_key"
        key_file.write_text(at_rest_key)
        key_file.chmod(0o600)

        # Build the all-in-one script (with at-rest encryption epilogue)
        script_content = build_session_script(
            job.steps,
            session_id=session.id,
            work_dir=str(work_dir),
            env=env,
            os_type="linux",
            encrypt_at_rest=True,
        )

        script_path = work_dir / "run.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o700)

        log_file_path = work_dir / "output.log"

        # Upload any script_file references
        self._stage_script_files(job.steps, work_dir)

        # Restrictive permissions on workspace
        work_dir.chmod(0o700)

        # Update session state
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

        # Launch detached — script handles its own logging to output.log
        proc = subprocess.Popen(
            ["bash", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=str(work_dir),
            env={
                **os.environ,
                "OFX_SESSION_ID": session.id,
                **env,
            },
        )

        session = session.model_copy(update={"remote_pid": proc.pid})
        self.store.save(session)
        logger.info("Local session %s started (PID %d)", session.id, proc.pid)
        return session

    # ------------------------------------------------------------------
    # Cloud submission
    # ------------------------------------------------------------------

    async def _submit_cloud(
        self,
        session: Session,
        job: Any,
        env: dict[str, str],
        cloud_profile: str,
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

        session = session.model_copy(
            update={
                "cloud_provider": resolved.provider or "static",
                "os_type": os_type,
                "ssh_user": resolved.ssh_user or "root",
                "ssh_port": resolved.ssh_port or 22,
                "ssh_key": resolved.ssh_key or "",
                "ssh_password": resolved.ssh_password or "",
            }
        )
        self.store.save(session)

        # Provision
        provider_name = resolved.provider or "static"
        provider_kwargs = _build_provider_kwargs(resolved)
        provider = CloudProviderRegistry.create(provider_name, **provider_kwargs)

        instance = await provider.create_instance(resolved)

        if provider_name != "static":
            instance = await provider.wait_until_ready(
                instance.instance_id, timeout=resolved.startup_timeout or 300
            )
            refreshed = await provider.get_instance(instance.instance_id)
            if refreshed and refreshed.ip:
                instance = refreshed

        if not instance or not instance.ip:
            session = session.model_copy(
                update={"status": SessionStatus.FAILED, "error": "No IP assigned"}
            )
            self.store.save(session)
            raise RuntimeError("Instance has no IP address")

        session = session.model_copy(
            update={
                "instance_id": instance.instance_id,
                "instance_ip": instance.ip,
            }
        )
        self.store.save(session)

        # Wait for connectivity
        await wait_for_connectivity(
            host=instance.ip,
            os_type="windows" if is_windows else "linux",
            ssh_port=resolved.ssh_port or 22,
            winrm_port=resolved.winrm_port or (5986 if resolved.winrm_ssl else 5985),
            timeout=180,
        )

        # Build script
        remote_work_dir = (
            f"C:\\Windows\\Temp\\ofx-session-{session.id}"
            if is_windows
            else f"/tmp/ofx-session-{session.id}"
        )

        # Generate at-rest encryption key
        at_rest_key = _secrets.token_hex(32)  # 64-char hex → 256-bit

        script_content = build_session_script(
            job.steps,
            session_id=session.id,
            work_dir=remote_work_dir,
            env=env,
            os_type=os_type,
            encrypt_at_rest=True,
        )

        session = session.model_copy(
            update={"at_rest_key": at_rest_key, "at_rest_encrypted": True}
        )

        # Create remote runner
        remote = _create_remote_runner(resolved, instance.ip)

        # Upload
        session = session.model_copy(update={"status": SessionStatus.UPLOADING})
        self.store.save(session)

        if is_windows:
            remote.run(f'mkdir "{remote_work_dir}" 2>nul')

            # Upload key file
            local_key = tempfile.mktemp(suffix=".key")
            Path(local_key).write_text(at_rest_key)
            try:
                remote.upload(local_key, f"{remote_work_dir}\\.ofx_key")
            finally:
                Path(local_key).unlink(missing_ok=True)

            # Upload script
            local_script = tempfile.mktemp(suffix=".ps1")
            Path(local_script).write_text(script_content)
            try:
                remote.upload(local_script, f"{remote_work_dir}\\run.ps1")
            finally:
                Path(local_script).unlink(missing_ok=True)

            # Restrictive permissions on remote dir
            remote.run(
                f'powershell "icacls \'{remote_work_dir}\' /inheritance:r '
                f'/grant:r \'$env:USERNAME:(OI)(CI)F\' /T 2>$null"',
            )

            # Stage script_file references
            self._upload_script_files(job.steps, remote, remote_work_dir, is_windows=True)

            # Start detached via PowerShell
            start_cmd = (
                f'Start-Process powershell -ArgumentList "-File {remote_work_dir}\\run.ps1" '
                f"-WindowStyle Hidden -PassThru | Select-Object -ExpandProperty Id"
            )
            pid_output = remote.run(f'powershell "{start_cmd}"').strip()
        else:
            remote.run(f"mkdir -p {remote_work_dir} && chmod 700 {remote_work_dir}")

            # Upload key file
            local_key = tempfile.mktemp(suffix=".key")
            Path(local_key).write_text(at_rest_key)
            try:
                remote.upload(local_key, f"{remote_work_dir}/.ofx_key")
            finally:
                Path(local_key).unlink(missing_ok=True)
            remote.run(f"chmod 600 {remote_work_dir}/.ofx_key")

            # Upload script
            local_script = tempfile.mktemp(suffix=".sh")
            Path(local_script).write_text(script_content)
            try:
                remote.upload(local_script, f"{remote_work_dir}/run.sh")
            finally:
                Path(local_script).unlink(missing_ok=True)

            remote.run(f"chmod 700 {remote_work_dir}/run.sh")

            # Stage script_file references
            self._upload_script_files(job.steps, remote, remote_work_dir, is_windows=False)

            # Start detached via nohup
            pid_output = remote.run(
                f"nohup bash {remote_work_dir}/run.sh "
                f"> {remote_work_dir}/output.log 2>&1 & echo $!"
            ).strip()

        # Parse PID
        try:
            pid = int(pid_output.strip().splitlines()[-1])
        except (ValueError, IndexError):
            pid = None

        remote_log = (
            f"{remote_work_dir}\\output.log"
            if is_windows
            else f"{remote_work_dir}/output.log"
        )

        session = session.model_copy(
            update={
                "status": SessionStatus.RUNNING,
                "remote_pid": pid,
                "remote_work_dir": remote_work_dir,
                "remote_log_file": remote_log,
                "output_path": str(self.store.session_dir(session.id)),
            }
        )
        self.store.save(session)
        logger.info(
            "Cloud session %s started on %s (PID %s)",
            session.id, instance.ip, pid,
        )

        # Cleanup remote runner (close ControlMaster etc.)
        if hasattr(remote, "cleanup"):
            remote.cleanup()

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
                    "finished_at": datetime.now(timezone.utc),
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
                        "finished_at": datetime.now(timezone.utc),
                    }
                )
            if marker == _FAIL_MARKER:
                return session.model_copy(
                    update={
                        "status": SessionStatus.FAILED,
                        "finished_at": datetime.now(timezone.utc),
                    }
                )
            return session  # Still running

        # Process exited — check log to determine outcome
        marker = _read_log_marker(Path(session.remote_log_file))
        if marker == _DONE_MARKER:
            return session.model_copy(
                update={
                    "status": SessionStatus.COMPLETED,
                    "finished_at": datetime.now(timezone.utc),
                }
            )
        return session.model_copy(
            update={
                "status": SessionStatus.FAILED,
                "error": "Process exited without success marker",
                "finished_at": datetime.now(timezone.utc),
            }
        )

    async def _check_cloud_status(self, session: Session) -> Session:
        """SSH in and check PID + log markers on a cloud VPS."""
        try:
            remote = self._reconnect(session)
        except Exception as exc:
            logger.debug("Cannot reconnect to %s: %s", session.instance_ip, exc)
            return session  # Can't determine — leave as-is

        try:
            if session.os_type == "windows":
                check_cmd = (
                    f"powershell \"(Get-Process -Id {session.remote_pid} "
                    f"-ErrorAction SilentlyContinue) -ne $null\""
                )
            else:
                check_cmd = f"kill -0 {session.remote_pid} 2>/dev/null && echo alive || echo dead"

            output = remote.run(check_cmd, timeout=15).strip()
            alive = "alive" in output.lower() or "true" in output.lower()

            # Check log marker
            if session.os_type == "windows":
                tail_cmd = f'powershell "Get-Content -Tail 5 {session.remote_log_file}"'
            else:
                tail_cmd = f"tail -5 {session.remote_log_file} 2>/dev/null"

            log_tail = remote.run(tail_cmd, timeout=15).strip()
            marker = _parse_marker(log_tail)

            if marker == _DONE_MARKER:
                return session.model_copy(
                    update={
                        "status": SessionStatus.COMPLETED,
                        "finished_at": datetime.now(timezone.utc),
                    }
                )
            if marker == _FAIL_MARKER or (not alive and marker is None):
                return session.model_copy(
                    update={
                        "status": SessionStatus.FAILED,
                        "error": "Process exited without success marker" if not marker else "",
                        "finished_at": datetime.now(timezone.utc),
                    }
                )

            return session  # Still running
        except Exception as exc:
            logger.debug("Status check failed for %s: %s", session.id, exc)
            return session
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    async def logs(
        self, session_id: str, tail: int = 50, follow: bool = False
    ) -> str:
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

        # Cloud: SSH in and tail
        try:
            remote = self._reconnect(session)
            if session.os_type == "windows":
                cmd = f'powershell "Get-Content -Tail {tail} {session.remote_log_file}"'
            else:
                cmd = f"tail -{tail} {session.remote_log_file} 2>/dev/null"
            output = remote.run(cmd, timeout=30)
            if hasattr(remote, "cleanup"):
                remote.cleanup()
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

        results = output_dir or self.store.results_dir(session_id)

        if session.target == SessionTarget.LOCAL:
            self._fetch_local_results(session, results)
        else:
            # Cloud — download via SCP
            await self._fetch_cloud_results(session, results)

        # Re-encrypt with user passphrase if requested
        if passphrase:
            enc_path = encrypt_results(results, passphrase)
            session = session.model_copy(
                update={
                    "status": SessionStatus.ENCRYPTED,
                    "encrypted": True,
                    "encrypted_file": str(enc_path),
                    "results_path": str(results),
                }
            )
        else:
            session = session.model_copy(
                update={
                    "status": SessionStatus.FETCHED,
                    "results_path": str(results),
                }
            )

        self.store.save(session)
        return results if not passphrase else Path(session.encrypted_file)

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
                if session.os_type == "windows":
                    enc_remote = f"{session.remote_work_dir}\\output.enc"
                else:
                    enc_remote = f"{session.remote_work_dir}/output.enc"

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
                    local_enc = None

                if local_enc and local_enc.exists():
                    _decrypt_at_rest_openssl(local_enc, session.at_rest_key, results)
                    local_enc.unlink(missing_ok=True)
                    # Also grab the log (not encrypted)
                    try:
                        remote.download(
                            session.remote_log_file, str(results / "output.log")
                        )
                    except Exception:
                        pass
                    return

            # Unencrypted fallback — download individual files
            if session.os_type == "windows":
                files_cmd = (
                    f'powershell "Get-ChildItem -Path \'{session.remote_work_dir}\\output\' '
                    f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
                )
            else:
                files_cmd = f"ls -1 {session.remote_work_dir}/output 2>/dev/null"

            output = remote.run(files_cmd, timeout=30)
            files = [f.strip() for f in output.strip().split("\n") if f.strip()]

            for fname in files:
                if session.os_type == "windows":
                    rpath = f"{session.remote_work_dir}\\output\\{fname}"
                else:
                    rpath = f"{session.remote_work_dir}/output/{fname}"
                try:
                    remote.download(rpath, str(results / fname))
                except Exception as exc:
                    logger.debug("Failed to download %s: %s", rpath, exc)

            # Also grab the log
            try:
                remote.download(session.remote_log_file, str(results / "output.log"))
            except Exception:
                pass
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()

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
                if session.os_type == "windows":
                    remote.run(
                        f"powershell \"Stop-Process -Id {session.remote_pid} -Force -ErrorAction SilentlyContinue\"",
                        timeout=15,
                    )
                else:
                    remote.run(f"kill {session.remote_pid} 2>/dev/null; sleep 1; kill -9 {session.remote_pid} 2>/dev/null", timeout=15)
                if hasattr(remote, "cleanup"):
                    remote.cleanup()
            except Exception as exc:
                logger.debug("Cancel failed for %s: %s", session_id, exc)

        session = session.model_copy(
            update={
                "status": SessionStatus.CANCELED,
                "finished_at": datetime.now(timezone.utc),
            }
        )
        self.store.save(session)
        return session

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
                cfg = CloudConfig(profile=session.cloud_profile) if session.cloud_profile else CloudConfig()
                mgr = get_cloud_profile_manager()
                resolved = mgr.resolve(cfg)
                provider_kwargs = _build_provider_kwargs(resolved)
                provider = CloudProviderRegistry.create(
                    session.cloud_provider or resolved.provider or "static",
                    **provider_kwargs,
                )
                await provider.destroy_instance(session.instance_id)
            except Exception as exc:
                logger.warning("Failed to destroy instance %s: %s", session.instance_id, exc)

        session = session.model_copy(
            update={
                "status": SessionStatus.DESTROYED,
                "finished_at": session.finished_at or datetime.now(timezone.utc),
            }
        )
        self.store.save(session)
        return session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_job(self, workflow: Any, job_id: str) -> Any:
        """Pick a job from the workflow."""
        # workflow.jobs is a dict[str, Job] keyed by jid
        jobs = workflow.jobs
        if isinstance(jobs, dict):
            if job_id:
                if job_id in jobs:
                    return jobs[job_id]
                raise ValueError(f"Job '{job_id}' not found in workflow")
            # Return first job
            if jobs:
                return next(iter(jobs.values()))
            raise ValueError("Workflow has no jobs")
        # Fallback for list-style
        if job_id:
            for job in jobs:
                if job.jid == job_id:
                    return job
            raise ValueError(f"Job '{job_id}' not found in workflow")
        if jobs:
            return jobs[0]
        raise ValueError("Workflow has no jobs")

    def _reconnect(self, session: Session) -> Any:
        """Create a PostSSH or PostWinRM to reconnect to a session's host."""
        from ofx.api.post import RunnerRegistry

        if session.os_type == "windows":
            return RunnerRegistry.create(
                "winrm",
                host=session.instance_ip,
                username=session.ssh_user,
                password=session.ssh_password,
                ssl=False,
                port=5985,
            )

        kwargs: dict[str, Any] = {
            "host": session.instance_ip,
            "user": session.ssh_user,
            "port": session.ssh_port or 22,
            "max_retries": 2,
        }
        if session.ssh_key:
            kwargs["identity_file"] = session.ssh_key
        if session.ssh_password:
            kwargs["password"] = session.ssh_password
        return RunnerRegistry.create("ssh", **kwargs)

    def _stage_script_files(self, steps: list, work_dir: Path) -> None:
        """Copy any script_file references into the local workspace."""
        from ofx.models.step import RunType

        for step in steps:
            if step.get_run_type() == RunType.SCRIPT_FILE:
                src = Path(step.script_file).expanduser().resolve()
                if src.exists():
                    dest = work_dir / src.name
                    shutil.copy2(str(src), str(dest))

    def _upload_script_files(
        self, steps: list, remote: Any, remote_work_dir: str, *, is_windows: bool
    ) -> None:
        """Upload any script_file references to the remote host."""
        from ofx.models.step import RunType

        for step in steps:
            if step.get_run_type() == RunType.SCRIPT_FILE:
                src = Path(step.script_file).expanduser().resolve()
                if src.exists():
                    if is_windows:
                        remote.upload(str(src), f"{remote_work_dir}\\{src.name}")
                    else:
                        remote.upload(str(src), f"{remote_work_dir}/{src.name}")


# ======================================================================
# Module-level helpers
# ======================================================================


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
    key_path = enc_file.parent / f".ofx_dec_{_secrets.token_hex(4)}"
    key_path.write_text(at_rest_key)
    key_path.chmod(0o600)

    tar_path = enc_file.parent / "output_dec.tar.gz"

    try:
        result = subprocess.run(
            [
                "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                "-iter", "100000",
                "-pass", f"file:{key_path}",
                "-in", str(enc_file),
                "-out", str(tar_path),
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
                if len(parts) > 1 and parts[0] == "output":
                    member.name = str(Path(*parts[1:]))
                elif parts[0] == "output":
                    continue  # skip the bare directory entry
                tar.extract(member, path=str(output_dir))

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
    except Exception:
        return None


def _parse_marker(text: str) -> str | None:
    """Find __OFX_DONE__ or __OFX_FAIL__ in text."""
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


def _build_provider_kwargs(cfg: Any) -> dict[str, Any]:
    """Build kwargs for CloudProviderRegistry.create() from a CloudConfig."""
    kwargs: dict[str, Any] = {}
    provider = cfg.provider or "static"

    if provider == "static":
        kwargs["host"] = getattr(cfg, "host", "") or ""
        kwargs["user"] = cfg.ssh_user or "root"
        kwargs["port"] = cfg.ssh_port or 22
        if cfg.ssh_key:
            kwargs["identity_file"] = cfg.ssh_key
        if cfg.ssh_password:
            kwargs["password"] = cfg.ssh_password
    elif provider == "digitalocean":
        token = (cfg.extra or {}).get("token") if hasattr(cfg, "extra") else None
        if not token and hasattr(cfg, "__pydantic_extra__"):
            token = (cfg.__pydantic_extra__ or {}).get("token")
        if token:
            kwargs["token"] = token
    elif provider == "aws":
        extras = {}
        if hasattr(cfg, "extra"):
            extras = cfg.extra or {}
        elif hasattr(cfg, "__pydantic_extra__"):
            extras = cfg.__pydantic_extra__ or {}
        for key in ("aws_access_key_id", "aws_secret_access_key", "region_name"):
            val = extras.get(key)
            if val:
                kwargs[key] = val
        kwargs["region"] = cfg.region or "us-east-1"

    return kwargs


def _create_remote_runner(cfg: Any, ip: str) -> Any:
    """Create PostSSH or PostWinRM for the given config + IP."""
    from ofx.api.post import RunnerRegistry

    os_type = getattr(cfg, "os", "linux") or "linux"
    if os_type == "windows":
        return RunnerRegistry.create(
            "winrm",
            host=ip,
            username=cfg.winrm_user or "Administrator",
            password=cfg.winrm_password or cfg.ssh_password or "",
            ssl=cfg.winrm_ssl or False,
            port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
        )
    return RunnerRegistry.create(
        "ssh",
        host=ip,
        user=cfg.ssh_user or "root",
        port=cfg.ssh_port or 22,
        identity_file=cfg.ssh_key or None,
        password=cfg.ssh_password or None,
        use_controlmaster=True,
        max_retries=3,
    )
