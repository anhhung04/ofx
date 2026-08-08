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
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

from ofx.cloud.sessions.encryption import decrypt_results, encrypt_results
from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.python_steps import (
    iter_python_step_bundles as _iter_python_step_bundles,
)
from ofx.cloud.runtime import remote_join
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.sessions.store import SessionStore
from ofx.cloud.temp_upload import upload_temp_content
from ofx.runner.profile_env import build_profile_env_overrides
from ofx.utils.file_cleanup import remove_files, remove_tree

logger = logging.getLogger("ofx")

_DONE_MARKER = "__TASK_OK__"
_FAIL_MARKER = "__TASK_ERR__"

_INITIAL_POLL_INTERVAL = 10.0
_MAX_POLL_INTERVAL = 120.0
_POLL_BACKOFF_FACTOR = 1.5
_MAX_CONSECUTIVE_FAILURES = 10
_SSH_COMMAND_TIMEOUT = 30

@dataclass(frozen=True)
class _ResolvedCloudSubmitState:
    os_type: str
    is_windows: bool
    session_update: dict[str, Any]

@dataclass(frozen=True)
class _PreparedCloudSubmitTarget:
    session: Session
    resolved: Any
    instance: Any
    os_type: str
    is_windows: bool

@dataclass(frozen=True)
class _PreparedCloudSubmitRuntime:
    session: Session
    remote_work_dir: str
    at_rest_key: str
    remote_log: str
    sep: str
    merged_env: dict[str, str]
    script_content: str
def _cloud_connection_settings(
    *,
    os_type: str,
    ssh_user: str = "root",
    ssh_port: int = 22,
    ssh_key: str = "",
    ssh_password: str = "",
    winrm_user: str = "Administrator",
    winrm_password: str = "",
    winrm_ssl: bool = False,
    winrm_port: int | None = None,
    winrm_transport: str = "ntlm",
) -> dict[str, Any]:
    normalized_os_type = os_type or "linux"
    normalized_winrm_ssl = bool(winrm_ssl)
    return {
        "os_type": normalized_os_type,
        "connection_type": "winrm" if normalized_os_type == "windows" else "ssh",
        "ssh_user": ssh_user or "root",
        "ssh_port": ssh_port or 22,
        "ssh_key": ssh_key or "",
        "ssh_password": ssh_password or "",
        "winrm_user": winrm_user or "Administrator",
        "winrm_password": winrm_password or "",
        "winrm_ssl": normalized_winrm_ssl,
        "winrm_port": winrm_port or (5986 if normalized_winrm_ssl else 5985),
        "winrm_transport": winrm_transport or "ntlm",
    }

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
        session_id = _secrets.token_hex(4)

        from ofx.settings import DEFAULT_WORKFLOWS_DIRS
        from ofx.utils.workflow_utils import find_workflow

        workflow = find_workflow(workflow_file, tuple(DEFAULT_WORKFLOWS_DIRS))
        session_steps, resolved_job_id = self._resolve_session_steps(workflow, job_id)
        workflow_name = workflow.name or Path(workflow_file).stem
        profile_name = workflow.defaults.profile or ""
        workflow_profile = None
        if profile_name:
            from ofx.profiles.manager import get_profile_manager

            workflow_profile = get_profile_manager().resolve_or_default(profile_name)
        if workflow_profile is not None and getattr(workflow_profile.time_window, "enabled", False):
            from ofx.profiles.time_window import check_time_window

            time_window_result = check_time_window(workflow_profile.time_window)
            if not time_window_result["allowed"]:
                raise RuntimeError(
                    f"Session submit aborted: {time_window_result['message']}"
                )
            if time_window_result["message"]:
                logger.warning(time_window_result["message"])

        merged_env = dict(env or {})
        if workflow_profile is not None:
            merged_env = build_profile_env_overrides(workflow_profile) | merged_env

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

        self.store.save(session)

        if target == SessionTarget.LOCAL:
            session = await self._submit_local(
                session,
                session_steps,
                merged_env,
                workflow_profile,
                workflow_dir=workflow.workflow_path.parent if workflow.workflow_path else None,
                workflow_name=workflow_name,
            )
        else:
            session = await self._submit_cloud(
                session,
                session_steps,
                merged_env,
                cloud_profile,
                workflow_profile,
                workflow_dir=workflow.workflow_path.parent if workflow.workflow_path else None,
                workflow_name=workflow_name,
            )

        return session

    def _save_session(self, session: Session, update: dict) -> Session:
        """Update session fields and persist to store."""
        session = session.model_copy(update=update)
        self.store.save(session)
        return session

    @staticmethod
    def _session_at_rest_update(at_rest_key: str) -> dict[str, Any]:
        return {
            "at_rest_key": at_rest_key,
            "at_rest_encrypted": True,
        }

    @staticmethod
    def _running_session_update(
        *,
        work_dir: str,
        log_file: str,
        output_path: str,
        os_type: str,
        at_rest_key: str,
        remote_pid: int | None = None,
        remote_tmux_session: str = "",
        remote_launcher: str = "",
    ) -> dict[str, Any]:
        update: dict[str, Any] = {
            "status": SessionStatus.RUNNING,
            "remote_work_dir": work_dir,
            "remote_log_file": log_file,
            "output_path": output_path,
            "os_type": os_type,
            **SessionManager._session_at_rest_update(at_rest_key),
        }
        if remote_pid is not None:
            update["remote_pid"] = remote_pid
        if remote_tmux_session:
            update["remote_tmux_session"] = remote_tmux_session
        if remote_launcher:
            update["remote_launcher"] = remote_launcher
        return update

    @staticmethod
    def _build_session_script_content(
        steps: list[Any],
        *,
        session: Session,
        work_dir: str,
        workflow_name: str,
        env: dict[str, str],
        profile: Any | None = None,
        os_type: str,
    ) -> str:
        return build_session_script(
            steps,
            session_id=session.id,
            work_dir=work_dir,
            workflow_name=workflow_name,
            job_name=session.job_id,
            env=env,
            profile=profile,
            os_type=os_type,
            encrypt_at_rest=True,
        )

    @classmethod
    def _resolved_cloud_submit_state(
        cls,
        resolved: Any,
    ) -> _ResolvedCloudSubmitState:
        connection = _cloud_connection_settings(
            os_type=getattr(resolved, "os", "linux") or "linux",
            ssh_user=getattr(resolved, "ssh_user", None) or "root",
            ssh_port=getattr(resolved, "ssh_port", None) or 22,
            ssh_key=getattr(resolved, "ssh_key", None) or "",
            ssh_password=getattr(resolved, "ssh_password", None) or "",
            winrm_user=getattr(resolved, "winrm_user", None) or "Administrator",
            winrm_ssl=bool(getattr(resolved, "winrm_ssl", False)),
            winrm_port=getattr(resolved, "winrm_port", None),
            winrm_transport=getattr(resolved, "winrm_transport", None) or "ntlm",
        )
        os_type = connection["os_type"]
        session_update = {
            "cloud_provider": getattr(resolved, "provider", None) or "static",
            "auto_destroy": bool(getattr(resolved, "auto_destroy", True)),
            "os_type": os_type,
            "ssh_user": connection["ssh_user"],
            "ssh_port": connection["ssh_port"],
            "ssh_key": connection["ssh_key"],
            "ssh_password": connection["ssh_password"],
            "winrm_port": connection["winrm_port"],
            "winrm_ssl": connection["winrm_ssl"],
            "winrm_transport": connection["winrm_transport"],
            "winrm_user": connection["winrm_user"],
        }

        return _ResolvedCloudSubmitState(
            os_type=os_type,
            is_windows=str(os_type).lower() == "windows",
            session_update=session_update,
        )

    async def _provision_submit_cloud_instance(
        self,
        session: Session,
        resolved: Any,
    ) -> tuple[Session, Any]:
        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.runtime import build_provider_kwargs

        provider_name = resolved.provider or "static"
        provider = CloudProviderRegistry.create(
            provider_name,
            **build_provider_kwargs(resolved),
        )
        instance = await provider.create_instance(resolved)

        try:
            if provider_name != "static":
                instance = await provider.wait_until_ready(
                    instance.instance_id,
                    timeout=resolved.startup_timeout or 300,
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
                session,
                {"status": SessionStatus.FAILED, "error": error_msg},
            )
            raise

        session = self._save_session(
            session,
            {"instance_id": instance.instance_id, "instance_ip": instance.ip},
        )
        return session, instance

    @staticmethod
    async def _await_submit_cloud_login(
        instance_ip: str,
        resolved: Any,
        *,
        is_windows: bool,
    ) -> None:
        from ofx.cloud.ssh import wait_for_connectivity, wait_for_login

        await wait_for_connectivity(
            host=instance_ip,
            os_type="windows" if is_windows else "linux",
            ssh_port=resolved.ssh_port or 22,
            winrm_port=resolved.winrm_port or (5986 if resolved.winrm_ssl else 5985),
            timeout=180,
        )
        await wait_for_login(
            host=instance_ip,
            cfg=resolved,
            timeout=getattr(resolved, "login_timeout", 300) or 300,
        )

    async def _prepare_cloud_submit_target(
        self,
        session: Session,
        cloud_profile: str,
    ) -> _PreparedCloudSubmitTarget:
        from ofx.cloud.config import get_cloud_profile_manager
        from ofx.models.cloud import CloudConfig

        resolved = get_cloud_profile_manager().resolve(
            CloudConfig(profile=cloud_profile) if cloud_profile else CloudConfig()
        )
        submit_state = self._resolved_cloud_submit_state(resolved)

        session = self._save_session(
            session,
            submit_state.session_update,
        )
        session, instance = await self._provision_submit_cloud_instance(
            session,
            resolved,
        )
        await self._await_submit_cloud_login(
            instance.ip,
            resolved,
            is_windows=submit_state.is_windows,
        )
        return _PreparedCloudSubmitTarget(
            session,
            resolved,
            instance,
            submit_state.os_type,
            submit_state.is_windows,
        )

    def _prepare_cloud_submit_runtime(
        self,
        steps: list[Any],
        *,
        session: Session,
        env: dict[str, str],
        profile: Any | None = None,
        workflow_name: str,
        os_type: str,
        is_windows: bool,
    ) -> _PreparedCloudSubmitRuntime:
        remote_work_dir = (
            f"C:\\Windows\\Temp\\.ses-{session.id}"
            if is_windows
            else f"/tmp/.ses-{session.id}"
        )
        at_rest_key = _secrets.token_hex(32)
        remote_log = f'{remote_work_dir}{"\\" if is_windows else "/"}output.log'
        sep = "\\" if is_windows else "/"
        merged_env = dict(env)
        for key, value in session.inputs.items():
            str_val = str(value)
            merged_env[key] = str_val
            upper_key = f"INPUT_{key.upper()}"
            if upper_key != key:
                merged_env[upper_key] = str_val
        prepared_session = session.model_copy(
            update=self._session_at_rest_update(at_rest_key)
        )
        script_content = self._build_session_script_content(
            steps,
            session=prepared_session,
            work_dir=remote_work_dir,
            workflow_name=workflow_name,
            env=merged_env,
            profile=profile,
            os_type=os_type,
        )
        return _PreparedCloudSubmitRuntime(
            session=prepared_session,
            remote_work_dir=remote_work_dir,
            at_rest_key=at_rest_key,
            remote_log=remote_log,
            sep=sep,
            merged_env=merged_env,
            script_content=script_content,
        )

    def _start_cloud_remote_submit(
        self,
        steps: list[Any],
        *,
        target: _PreparedCloudSubmitTarget,
        runtime: _PreparedCloudSubmitRuntime,
        profile: Any | None = None,
        workflow_dir: Path | None,
        workflow_name: str,
    ) -> Session:
        from ofx.cloud.runtime import create_remote_runner

        remote = create_remote_runner(
            target.resolved,
            target.instance.ip,
            max_retries=3,
        )

        def _pid_or_none(pid_output: str) -> int | None:
            try:
                return int(pid_output.strip().splitlines()[-1])
            except (ValueError, IndexError):
                return None

        try:
            session = self._save_session(
                runtime.session,
                {"status": SessionStatus.UPLOADING},
            )

            if target.is_windows:
                remote.run(f'mkdir "{runtime.remote_work_dir}" 2>nul')
            else:
                remote.run(
                    f"mkdir -p {runtime.remote_work_dir} && chmod 700 {runtime.remote_work_dir}"
                )
            merged_env = runtime.merged_env
            file_overrides: dict[str, str] = {}
            for key, value in session.inputs.items():
                str_val = str(value)
                local = Path(str_val)
                if not local.is_file():
                    continue

                remote_path = f"{runtime.remote_work_dir}{runtime.sep}{local.name}"
                try:
                    remote.upload(str_val, remote_path)
                    file_overrides[key] = remote_path
                    file_overrides[f"INPUT_{key.upper()}"] = remote_path
                    logger.debug(
                        "Uploaded session input file %s → %s", str_val, remote_path
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to upload session input file '{str_val}' "
                        f"to '{remote_path}': {exc}"
                    ) from exc

            if file_overrides:
                merged_env = {**merged_env, **file_overrides}

            script_content = self._build_session_script_content(
                steps,
                session=session,
                work_dir=runtime.remote_work_dir,
                workflow_name=workflow_name,
                env=merged_env,
                profile=profile,
                os_type=target.os_type,
            )
            upload_temp_content(
                remote,
                runtime.at_rest_key,
                f"{runtime.remote_work_dir}{runtime.sep}.skey",
                suffix=".key",
            )
            ext = ".ps1" if target.is_windows else ".sh"
            upload_temp_content(
                remote,
                script_content,
                f"{runtime.remote_work_dir}{runtime.sep}run{ext}",
                suffix=ext,
            )
            if target.is_windows:
                remote.run(
                    f"powershell \"icacls '{runtime.remote_work_dir}' /inheritance:r "
                    f"/grant:r '$env:USERNAME:(OI)(CI)F' /T 2>$null\"",
                )
            else:
                remote.run(f"chmod 600 {runtime.remote_work_dir}/.skey")
                remote.run(f"chmod 700 {runtime.remote_work_dir}/run.sh")

            self._upload_script_files(
                steps,
                remote,
                runtime.remote_work_dir,
                is_windows=target.is_windows,
                workflow_dir=workflow_dir,
            )

            if target.is_windows:
                start_cmd = (
                    f'Start-Process powershell -ArgumentList "-File {runtime.remote_work_dir}\\run.ps1" '
                    f"-WindowStyle Hidden -PassThru | Select-Object -ExpandProperty Id"
                )
                pid_output = remote.run(f'powershell "{start_cmd}"').strip()
                remote_pid = _pid_or_none(pid_output)
                remote_launcher = "start-process"
                remote_tmux_session = ""
            else:
                tmux_name = f"ofx-ses-{session.id}"
                has_tmux = (
                    remote.run("command -v tmux >/dev/null 2>&1 && echo yes || echo no")
                    .strip()
                    .lower()
                    == "yes"
                )
                if has_tmux:
                    remote_run_script = f"{runtime.remote_work_dir}/run.sh"
                    remote_out_log = f"{runtime.remote_work_dir}/output.log"
                    tmux_cmd = (
                        f"bash {shlex.quote(str(remote_run_script))} >> "
                        f"{shlex.quote(str(remote_out_log))} 2>&1"
                    )
                    remote.run(
                        f"tmux new-session -d -s {shlex.quote(str(tmux_name))} "
                        f"{shlex.quote(str(tmux_cmd))}"
                    )
                    pid_output = remote.run(
                        f"tmux list-panes -t {shlex.quote(str(tmux_name))} "
                        "-F '#{pane_pid}' 2>/dev/null | head -n1"
                    ).strip()
                    remote_pid = _pid_or_none(pid_output)
                    remote_launcher = "tmux"
                    remote_tmux_session = tmux_name
                else:
                    remote_run_script = f"{runtime.remote_work_dir}/run.sh"
                    remote_out_log = f"{runtime.remote_work_dir}/output.log"
                    pid_output = remote.run(
                        f"nohup bash {shlex.quote(str(remote_run_script))} > "
                        f"{shlex.quote(str(remote_out_log))} 2>&1 & echo $!"
                    ).strip()
                    remote_pid = _pid_or_none(pid_output)
                    remote_launcher = "nohup"
                    remote_tmux_session = ""

            return self._save_session(
                session,
                self._running_session_update(
                    work_dir=runtime.remote_work_dir,
                    log_file=runtime.remote_log,
                    output_path=str(self.store.session_dir(session.id)),
                    os_type=target.os_type,
                    at_rest_key=runtime.at_rest_key,
                    remote_pid=remote_pid,
                    remote_tmux_session=remote_tmux_session,
                    remote_launcher=remote_launcher,
                ),
            )
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()

    def _mark_completed(self, session: Session) -> Session:
        return session.model_copy(
            update=self._finished_session_update(SessionStatus.COMPLETED)
        )

    def _mark_failed(self, session: Session, *, error: str = "") -> Session:
        return session.model_copy(
            update=self._finished_session_update(
                SessionStatus.FAILED,
                error=error,
            )
        )

    @staticmethod
    def _finished_session_update(
        status: SessionStatus,
        *,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        update: dict[str, Any] = {
            "status": status,
            "finished_at": finished_at or datetime.now(UTC),
        }
        if error is not None:
            update["error"] = error
        return update

    def _save_fetched_results(self, session: Session, results: Path) -> Session:
        return self._save_session(
            session,
            {
                "status": SessionStatus.FETCHED,
                "results_path": str(results),
            },
        )

    def _save_encrypted_results(
        self,
        session: Session,
        *,
        encrypted_file: Path,
        results: Path,
    ) -> Session:
        return self._save_session(
            session,
            {
                "status": SessionStatus.ENCRYPTED,
                "encrypted": True,
                "encrypted_file": str(encrypted_file),
                "results_path": str(results),
            },
        )

    @staticmethod
    def _prepare_results_dir(results: Path) -> None:
        results.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _results_log_path(results: Path) -> Path:
        return results / "output.log"

    @staticmethod
    def _session_encrypted_results_path(work_dir: str | Path) -> Path:
        return Path(work_dir) / "output.enc"

    @staticmethod
    def _session_output_dir(work_dir: str | Path) -> Path:
        return Path(work_dir) / "output"

    @classmethod
    def _copy_output_entry(cls, entry: Path, results: Path) -> None:
        destination = results / entry.name
        if entry.is_file():
            shutil.copy2(str(entry), str(destination))
            return
        if entry.is_dir():
            shutil.copytree(str(entry), str(destination), dirs_exist_ok=True)

    @classmethod
    def _copy_output_dir(cls, output_dir: Path, results: Path) -> None:
        if not output_dir.exists():
            return
        for entry in output_dir.iterdir():
            cls._copy_output_entry(entry, results)

    @classmethod
    def _copy_log_file(cls, log_path: Path, results: Path) -> None:
        if not log_path.exists():
            return
        shutil.copy2(str(log_path), str(cls._results_log_path(results)))

    @staticmethod
    def _remote_encrypted_results_path(session: Session) -> str:
        return remote_join(
            session.remote_work_dir,
            "output.enc",
            is_windows=session.os_type == "windows",
        )

    @staticmethod
    def _remote_output_dir_path(session: Session) -> str:
        return remote_join(
            session.remote_work_dir,
            "output",
            is_windows=session.os_type == "windows",
        )

    @staticmethod
    def _remote_output_file_path(session: Session, filename: str) -> str:
        return remote_join(
            session.remote_work_dir,
            "output",
            filename,
            is_windows=session.os_type == "windows",
        )

    @classmethod
    def _remote_output_list_command(cls, session: Session) -> str:
        output_dir = cls._remote_output_dir_path(session)
        if session.os_type == "windows":
            return (
                f"powershell \"Get-ChildItem -Path '{output_dir}' "
                f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
            )
        return f"ls -1 {shlex.quote(str(output_dir))} 2>/dev/null"

    @staticmethod
    def _remote_output_names(output: str) -> list[str]:
        return [line.strip() for line in output.splitlines() if line.strip()]

    @staticmethod
    def _download_optional_remote_file(
        remote: Any,
        remote_path: str,
        local_path: Path,
        *,
        label: str,
    ) -> bool:
        try:
            remote.download(remote_path, str(local_path))
            return True
        except Exception as exc:
            logger.debug("Failed to download %s %s: %s", label, remote_path, exc)
            return False

    def _download_remote_log(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> None:
        self._download_optional_remote_file(
            remote,
            session.remote_log_file,
            self._results_log_path(results),
            label="remote log",
        )

    def _download_remote_output_files(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> None:
        output = remote.run(self._remote_output_list_command(session), timeout=30)
        for filename in self._remote_output_names(output):
            self._download_optional_remote_file(
                remote,
                self._remote_output_file_path(session, filename),
                results / filename,
                label="remote output",
            )

    def _download_encrypted_results_archive(
        self,
        remote: Any,
        session: Session,
        results: Path,
    ) -> bool:
        if not session.at_rest_encrypted:
            return False

        local_archive = results.parent / f"output_{session.id}.enc"
        try:
            remote.download(
                self._remote_encrypted_results_path(session),
                str(local_archive),
            )
        except Exception as exc:
            logger.warning(
                "Encrypted archive not found on VPS (%s); "
                "falling back to unencrypted fetch",
                exc,
            )
            return False

        if not local_archive.exists():
            return False

        try:
            _decrypt_at_rest_openssl(local_archive, session.at_rest_key, results)
            return True
        finally:
            remove_files([local_archive])

    @staticmethod
    def _bundle_manifest(session: Session) -> dict[str, Any]:
        return {
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

    async def _ensure_results_dir(self, session_id: str) -> tuple[Session, Path]:
        session = self.store.load(session_id)
        results_dir = Path(session.results_path) if session.results_path else None
        if results_dir is not None and results_dir.exists():
            return session, results_dir

        if session.status in (
            SessionStatus.COMPLETED,
            SessionStatus.FETCHED,
            SessionStatus.ENCRYPTED,
        ):
            await self.fetch(session_id)
            session = self.store.load(session_id)
            results_dir = Path(session.results_path) if session.results_path else None

        if results_dir is None or not results_dir.exists():
            raise RuntimeError(
                f"No fetched results available for session {session_id}. "
                "Run 'ofx session fetch <id>' first."
            )
        return session, results_dir

    def _status_from_marker(
        self,
        session: Session,
        marker: str | None,
        *,
        missing_error: str = "",
    ) -> Session | None:
        if marker == _DONE_MARKER:
            return self._mark_completed(session)
        if marker == _FAIL_MARKER:
            return self._mark_failed(session)
        if missing_error:
            return self._mark_failed(session, error=missing_error)
        return None

    def _reset_poll_failures(self, session_id: str) -> None:
        self._poll_failures[session_id] = 0

    @staticmethod
    def _cancel_local_execution(session: Session) -> None:
        if session.remote_pid is None:
            return

        pid = session.remote_pid
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            with suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
            pgid = None
        else:
            # Give processes a moment to exit gracefully, then SIGKILL
            import time
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.killpg(pgid, 0)
                except (OSError, ProcessLookupError):
                    break
                time.sleep(0.1)
            else:
                with suppress(OSError, ProcessLookupError):
                    os.killpg(pgid, signal.SIGKILL)

        # Reap all zombies in the process group
        if pgid is not None:
            try:
                while True:
                    wpid, _status = os.waitpid(-pgid, os.WNOHANG)
                    if wpid == 0:
                        break
            except ChildProcessError:
                pass
        # Fallback: reap the direct child
        try:
            while True:
                wpid, _status = os.waitpid(pid, os.WNOHANG)
                if wpid == 0:
                    break
        except ChildProcessError:
            pass

    def _with_reconnected_remote(
        self,
        session: Session,
        operation: Callable[[Any], Any],
    ) -> Any:
        remote = self._reconnect(session)
        try:
            return operation(remote)
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()

    @staticmethod
    def _resolved_project_path(
        project: str,
        *,
        error_message: str,
    ) -> Path | None:
        if not project:
            return None

        try:
            from ofx.commands.project.project_manager import ProjectManager

            project_path = Path(ProjectManager.resolve_path(project))
        except Exception as exc:
            logger.debug(error_message, exc)
            return None

        if not project_path.exists():
            return None
        return project_path

    def _add_project_logs_to_bundle(self, bundle: tarfile.TarFile, session: Session) -> None:
        project_path = self._resolved_project_path(
            session.project,
            error_message="Project log path resolution failed: %s",
        )
        if project_path is None:
            return

        logs_dir = project_path / "logs"
        if not logs_dir.exists():
            return
        bundle.add(logs_dir, arcname="project_logs")

    async def _destroy_session_instance(
        self,
        session: Session,
        *,
        clear_instance_fields: bool,
        warning_message: str,
    ) -> Session:
        if session.target != SessionTarget.CLOUD or not session.instance_id:
            return session
        if (session.cloud_provider or "static") == "static":
            return session

        try:
            from ofx.cloud import CloudProviderRegistry
            from ofx.cloud.config import get_cloud_profile_manager
            from ofx.cloud.runtime import build_provider_kwargs
            from ofx.models.cloud import CloudConfig

            resolved = get_cloud_profile_manager().resolve(
                CloudConfig(profile=session.cloud_profile)
                if session.cloud_profile
                else CloudConfig()
            )
            provider = CloudProviderRegistry.create(
                session.cloud_provider or getattr(resolved, "provider", None) or "static",
                **build_provider_kwargs(resolved),
            )
            await provider.destroy_instance(session.instance_id)
            if clear_instance_fields:
                return self._save_session(
                    session,
                    {"instance_id": "", "instance_ip": ""},
                )
            return session
        except Exception as exc:
            logger.warning(warning_message, session.id, session.instance_id, exc)
            return session

    def _poll_failure_result(
        self,
        session: Session,
        exc: Exception,
        *,
        debug_message: str,
        debug_args: tuple[Any, ...],
    ) -> Session:
        count = self._poll_failures.get(session.id, 0) + 1
        self._poll_failures[session.id] = count
        backoff = min(
            _INITIAL_POLL_INTERVAL * (_POLL_BACKOFF_FACTOR**count),
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
                    "error": (
                        f"Unreachable after {count} consecutive poll failures: {exc}"
                    ),
                }
            )

        logger.debug(debug_message, *debug_args, count, backoff, exc)
        return session

    def _ensure_poll_failures(self) -> None:
        if not hasattr(self, "_poll_failures"):
            self._poll_failures = {}

    def _with_cloud_remote_probe(
        self,
        session: Session,
        *,
        reconnect_error: str,
        reconnect_args: tuple[Any, ...],
        probe_error: str,
        probe_args: tuple[Any, ...],
        probe: Callable[[Any], Session],
    ) -> Session:
        try:
            remote = self._reconnect(session)
        except Exception as exc:
            return self._poll_failure_result(
                session,
                exc,
                debug_message=reconnect_error,
                debug_args=reconnect_args,
            )

        try:
            return probe(remote)
        except Exception as exc:
            return self._poll_failure_result(
                session,
                exc,
                debug_message=probe_error,
                debug_args=probe_args,
            )
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()

    def _check_cloud_status_without_pid(self, session: Session) -> Session:
        def _probe(remote: Any) -> Session:
            tail_cmd = (
                f'powershell "Get-Content -Tail 5 {session.remote_log_file}"'
                if session.os_type == "windows"
                else f"tail -5 {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
            )
            log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
            marker = None
            if _DONE_MARKER in log_tail:
                marker = _DONE_MARKER
            elif _FAIL_MARKER in log_tail:
                marker = _FAIL_MARKER

            self._reset_poll_failures(session.id)

            marker_status = self._status_from_marker(session, marker)
            if marker_status is not None:
                return marker_status
            if (
                session.os_type != "windows"
                and session.remote_launcher == "tmux"
                and session.remote_tmux_session
            ):
                tmux_alive = remote.run(
                    f"tmux has-session -t {shlex.quote(str(session.remote_tmux_session))} "
                    "2>/dev/null && echo alive || echo dead",
                    timeout=_SSH_COMMAND_TIMEOUT,
                )
                if "alive" in tmux_alive.strip().lower():
                    return session
            return session

        return self._with_cloud_remote_probe(
            session,
            reconnect_error=(
                "Status check (no-pid) failed for %s "
                "(attempt %d, next backoff %.1fs): %s"
            ),
            reconnect_args=(session.id,),
            probe_error=(
                "Status check (no-pid) failed for %s "
                "(attempt %d, next backoff %.1fs): %s"
            ),
            probe_args=(session.id,),
            probe=_probe,
        )

    def _check_cloud_status_with_pid(self, session: Session) -> Session:
        def _probe(remote: Any) -> Session:
            if session.os_type == "windows":
                check_cmd = (
                    f'powershell "(Get-Process -Id {session.remote_pid} '
                    f'-ErrorAction SilentlyContinue) -ne $null"'
                )
            elif session.remote_launcher == "tmux" and session.remote_tmux_session:
                check_cmd = (
                    f"tmux has-session -t {shlex.quote(str(session.remote_tmux_session))} 2>/dev/null "
                    "&& echo alive || echo dead"
                )
            else:
                check_cmd = (
                    f"kill -0 {session.remote_pid} 2>/dev/null && echo alive || echo dead"
                )
            output = remote.run(check_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip().lower()
            alive = "alive" in output or "true" in output
            tail_cmd = (
                f'powershell "Get-Content -Tail 5 {session.remote_log_file}"'
                if session.os_type == "windows"
                else f"tail -5 {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
            )
            log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
            marker = None
            if _DONE_MARKER in log_tail:
                marker = _DONE_MARKER
            elif _FAIL_MARKER in log_tail:
                marker = _FAIL_MARKER

            self._reset_poll_failures(session.id)
            marker_status = self._status_from_marker(session, marker)
            if marker_status is not None:
                return marker_status
            if alive:
                return session
            return self._mark_failed(
                session, error="Process exited without success marker"
            )

        return self._with_cloud_remote_probe(
            session,
            reconnect_error=(
                "Cannot reconnect to %s (attempt %d, next backoff %.1fs): %s"
            ),
            reconnect_args=(session.instance_ip,),
            probe_error=(
                "Status check failed for %s (attempt %d, next backoff %.1fs): %s"
            ),
            probe_args=(session.id,),
            probe=_probe,
        )

    async def _submit_local(
        self,
        session: Session,
        steps: list[Any],
        env: dict[str, str],
        profile: Any | None = None,
        *,
        workflow_dir: Path | None,
        workflow_name: str,
    ) -> Session:
        """Start workflow steps as a detached local background process."""
        session_dir = self.store.session_dir(session.id)
        work_dir = session_dir / "workspace"
        output_dir = work_dir / "output"
        log_file_path = work_dir / "output.log"
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(exist_ok=True)

        at_rest_key = _secrets.token_hex(32)
        key_file = work_dir / ".skey"
        key_file.write_text(at_rest_key)
        key_file.chmod(0o600)

        merged_env = dict(env)
        for key, value in session.inputs.items():
            str_val = str(value)
            merged_env[key] = str_val
            upper_key = f"INPUT_{key.upper()}"
            if upper_key != key:
                merged_env[upper_key] = str_val
        for key, value in session.inputs.items():
            local = Path(str(value))
            if not local.is_file():
                continue

            dest = work_dir / local.name
            try:
                shutil.copy2(str(local), str(dest))
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to stage session input file '{local}': {exc}"
                ) from exc

            dest_str = str(dest)
            merged_env[key] = dest_str
            merged_env[f"INPUT_{key.upper()}"] = dest_str
            logger.debug("Staged session input file %s → %s", local, dest)

        script_content = self._build_session_script_content(
            steps,
            session=session,
            work_dir=str(work_dir),
            workflow_name=workflow_name,
            env=merged_env,
            profile=profile,
            os_type="linux",
        )

        script_path = work_dir / "run.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o700)
        self._stage_script_files(steps, work_dir, workflow_dir=workflow_dir)
        work_dir.chmod(0o700)

        session = session.model_copy(
            update=self._running_session_update(
                work_dir=str(work_dir),
                log_file=str(log_file_path),
                output_path=str(session_dir),
                os_type="linux",
                at_rest_key=at_rest_key,
            )
        )

        child_env = {**os.environ, "SESSION_ID": session.id, **merged_env}
        # Prevent grpc C extension from re-enabling the GIL in free-threaded
        # Python builds — toggling the GIL during subprocess spawn can
        # destabilise the parent process (CodeWhale, VS Code, etc.).
        child_env.setdefault("PYTHON_GIL", "0")

        pid = subprocess.Popen(
            ["bash", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=False,
            cwd=str(work_dir),
            env=child_env,
        )
        pid = pid.pid

        session = self._save_session(session, {"remote_pid": pid})
        logger.info("Local session %s started (PID %d)", session.id, pid)
        return session

    async def _submit_cloud(
        self,
        session: Session,
        steps: list[Any],
        env: dict[str, str],
        cloud_profile: str,
        profile: Any | None = None,
        *,
        workflow_dir: Path | None,
        workflow_name: str,
    ) -> Session:
        """Provision a VPS, upload the script, and start detached via SSH/WinRM."""
        target = await self._prepare_cloud_submit_target(session, cloud_profile)
        runtime = self._prepare_cloud_submit_runtime(
            steps,
            session=target.session,
            env=env,
            profile=profile,
            workflow_name=workflow_name,
            os_type=target.os_type,
            is_windows=target.is_windows,
        )
        session = self._start_cloud_remote_submit(
            steps,
            target=target,
            runtime=runtime,
            profile=profile,
            workflow_dir=workflow_dir,
            workflow_name=workflow_name,
        )
        logger.info(
            "Cloud session %s started on %s (PID %s)",
            session.id,
            target.instance.ip,
            session.remote_pid,
        )

        return session

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
            return self._mark_failed(session, error="No PID recorded")

        try:
            os.kill(session.remote_pid, 0)
        except (ProcessLookupError, PermissionError):
            alive = False
        else:
            try:
                with open(f"/proc/{session.remote_pid}/status") as fh:
                    alive = True
                    for line in fh:
                        if line.startswith("State:"):
                            alive = "Z" not in line
                            break
            except (FileNotFoundError, PermissionError, OSError):
                alive = True

        log_path = Path(session.remote_log_file)
        if not log_path.exists():
            marker = None
        else:
            try:
                log_text = log_path.read_text(errors="replace")
                if _DONE_MARKER in log_text:
                    marker = _DONE_MARKER
                elif _FAIL_MARKER in log_text:
                    marker = _FAIL_MARKER
                else:
                    marker = None
            except Exception as exc:
                logger.debug("Failed to read status file %s: %s", log_path, exc)
                marker = None

        marker_status = self._status_from_marker(session, marker)
        if marker_status is not None:
            return marker_status
        if alive:
            return session
        return self._mark_failed(
            session, error="Process exited without success marker"
        )

    async def _check_cloud_status(self, session: Session) -> Session:
        """SSH in and check PID + log markers on a cloud VPS.

        Tracks consecutive connection failures per session.  After
        *_MAX_CONSECUTIVE_FAILURES* the session is marked ``UNREACHABLE``.
        On a successful probe the failure counter resets to zero.
        """
        self._ensure_poll_failures()

        if session.remote_pid is None:
            return self._check_cloud_status_without_pid(session)
        return self._check_cloud_status_with_pid(session)

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
            try:
                return "\n".join(
                    log_path.read_text(errors="replace").splitlines()[-tail:]
                )
            except Exception:
                return "(cannot read log)"

        try:
            def _read_remote_logs(remote: Any) -> str:
                cmd = (
                    f'powershell "Get-Content -Tail {tail} {session.remote_log_file}"'
                    if session.os_type == "windows"
                    else f"tail -{tail} {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
                )
                return remote.run(cmd, timeout=30)

            return self._with_reconnected_remote(session, _read_remote_logs)
        except Exception as exc:
            return f"(cannot retrieve logs: {exc})"

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
        session = await self.status(session_id)

        if session.is_running():
            raise RuntimeError(
                f"Session {session_id} is still running (status={session.status.value}). "
                "Wait for completion or cancel first."
            )

        results = output_dir or self._resolve_results_dir(session)

        if session.target == SessionTarget.LOCAL:
            self._fetch_local_results(session, results)
        else:
            await self._fetch_cloud_results(session, results)
            session = await self._auto_destroy_after_fetch(session)

        if passphrase:
            enc_path = encrypt_results(results, passphrase)
            session = self._save_encrypted_results(
                session,
                encrypted_file=enc_path,
                results=results,
            )
        else:
            session = self._save_fetched_results(session, results)

        return results if not passphrase else Path(session.encrypted_file)

    async def _auto_destroy_after_fetch(self, session: Session) -> Session:
        """Auto-destroy cloud instance after fetch when configured and non-static."""
        if session.target != SessionTarget.CLOUD:
            return session
        if not session.instance_id:
            return session
        if not session.auto_destroy:
            return session
        return await self._destroy_session_instance(
            session,
            clear_instance_fields=True,
            warning_message="Auto-destroy after fetch failed for session %s (instance %s): %s",
        )

    def _fetch_local_results(self, session: Session, results: Path) -> None:
        """Copy local session output to results dir, decrypting if needed."""
        work_dir = Path(session.remote_work_dir)
        self._prepare_results_dir(results)

        enc_file = self._session_encrypted_results_path(work_dir)
        if session.at_rest_encrypted and enc_file.exists():
            _decrypt_at_rest_openssl(enc_file, session.at_rest_key, results)
        else:
            self._copy_output_dir(self._session_output_dir(work_dir), results)

        self._copy_log_file(Path(session.remote_log_file), results)

    async def _fetch_cloud_results(self, session: Session, results: Path) -> None:
        """Download output from a cloud VPS via SCP, decrypting if needed."""
        def _download_results(remote: Any) -> None:
            self._prepare_results_dir(results)

            if self._download_encrypted_results_archive(remote, session, results):
                self._download_remote_log(remote, session, results)
                return

            self._download_remote_output_files(remote, session, results)
            self._download_remote_log(remote, session, results)

        self._with_reconnected_remote(session, _download_results)

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

    async def cancel(self, session_id: str) -> Session:
        """Kill the running process and mark session as canceled."""
        session = self.store.load(session_id)

        if not session.is_running():
            return session

        if session.target == SessionTarget.LOCAL:
            self._cancel_local_execution(session)
        else:
            try:
                self._with_reconnected_remote(
                    session,
                    lambda remote: (
                        remote.run(
                            f'powershell "Stop-Process -Id {session.remote_pid} -Force -ErrorAction SilentlyContinue"',
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.os_type == "windows"
                        else remote.run(
                            f"tmux kill-session -t {shlex.quote(str(session.remote_tmux_session))} 2>/dev/null || true",
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.remote_launcher == "tmux" and session.remote_tmux_session
                        else remote.run(
                            f"kill {session.remote_pid} 2>/dev/null; sleep 1; kill -9 {session.remote_pid} 2>/dev/null",
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.remote_pid
                        else None
                    ),
                )
            except Exception as exc:
                logger.debug("Cancel failed for %s: %s", session.id, exc)

        return self._save_session(
            session,
            self._finished_session_update(SessionStatus.CANCELED),
        )

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

        remove_tree(
            Path(session.remote_work_dir)
            if session.target == SessionTarget.LOCAL and session.remote_work_dir
            else None,
            on_error=logger.warning,
            label="session workspace",
        )

        if session.target == SessionTarget.CLOUD and session.instance_id:
            session = await self._destroy_session_instance(
                session,
                clear_instance_fields=False,
                warning_message="Failed to destroy session %s instance %s: %s",
            )

        return self._save_session(
            session,
            self._finished_session_update(
                SessionStatus.DESTROYED,
                finished_at=session.finished_at,
            ),
        )

    async def bundle_artifacts(
        self,
        session_id: str,
        *,
        output_file: Path | None = None,
        include_project_context: bool = True,
    ) -> Path:
        """Create a tar.gz bundle with session metadata + fetched artifacts."""
        session_dir = self.store.session_dir(session_id)
        session, results_dir = await self._ensure_results_dir(session_id)

        bundle_path = output_file or (session_dir / f"bundle_{session_id}.tar.gz")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        manifest_path = session_dir / f"bundle_manifest_{session.id}.json"
        manifest_path.write_text(json.dumps(self._bundle_manifest(session), indent=2))
        try:
            with tarfile.open(bundle_path, "w:gz") as tf:
                tf.add(manifest_path, arcname="manifest.json")
                tf.add(session_dir / "session.json", arcname="session.json")
                if results_dir.exists():
                    tf.add(results_dir, arcname="results")
                if include_project_context and session.project:
                    self._add_project_logs_to_bundle(tf, session)
        finally:
            remove_files([manifest_path])

        return bundle_path

    def _resolve_results_dir(self, session: Session) -> Path:
        """Resolve where to store fetched results.

        If the session is associated with a project, results go into
        ``<project_path>/evidence/sessions/<session_id>/``.
        Otherwise falls back to ``~/.ofx/sessions/<id>/results/``.
        """
        project_path = self._resolved_project_path(
            session.project,
            error_message="Project evidence path resolution failed: %s",
        )
        if project_path is not None:
            project_results_dir = project_path / "evidence" / "sessions" / session.id
            project_results_dir.mkdir(parents=True, exist_ok=True)
            return project_results_dir
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

        from ofx.runner.workflow_scheduler import WorkflowScheduler

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
        from ofx.models.cloud import CloudConfig
        from ofx.cloud.runtime import create_remote_runner

        connection = _cloud_connection_settings(
            os_type=session.os_type or "linux",
            ssh_user=session.ssh_user or "root",
            ssh_port=session.ssh_port or 22,
            ssh_key=session.ssh_key or "",
            ssh_password=session.ssh_password or "",
            winrm_user=session.winrm_user or session.ssh_user or "Administrator",
            winrm_password=session.ssh_password or "",
            winrm_ssl=session.winrm_ssl or False,
            winrm_port=session.winrm_port,
            winrm_transport=session.winrm_transport or "ntlm",
        )
        cfg = CloudConfig(
            provider=session.cloud_provider or "static",
            os=connection["os_type"],
            connection_type=connection["connection_type"],
            ssh_user=connection["ssh_user"],
            ssh_port=connection["ssh_port"],
            ssh_key=connection["ssh_key"],
            ssh_password=connection["ssh_password"],
            winrm_user=connection["winrm_user"],
            winrm_password=connection["winrm_password"],
            winrm_ssl=connection["winrm_ssl"],
            winrm_port=connection["winrm_port"],
            winrm_transport=connection["winrm_transport"],
        )
        return create_remote_runner(cfg, session.instance_ip, max_retries=2)

    def _stage_script_files(
        self,
        steps: list,
        work_dir: Path,
        *,
        workflow_dir: Path | None = None,
    ) -> None:
        """Stage bundled Python step artifacts into the local workspace."""
        for _idx, filename, bundle_source in _iter_python_step_bundles(
            steps,
            workflow_dir=workflow_dir,
        ):
            dest = work_dir / filename
            dest.write_text(bundle_source)
            dest.chmod(0o600)

    def _upload_script_files(
        self,
        steps: list,
        remote: Any,
        remote_work_dir: str,
        *,
        is_windows: bool,
        workflow_dir: Path | None = None,
    ) -> None:
        """Upload bundled Python step artifacts to the remote host."""
        for _idx, filename, bundle_source in _iter_python_step_bundles(
            steps,
            workflow_dir=workflow_dir,
        ):
            remote_path = (
                f"{remote_work_dir}\\{filename}"
                if is_windows
                else f"{remote_work_dir}/{filename}"
            )
            upload_temp_content(
                remote,
                bundle_source,
                remote_path,
                suffix=".py",
            )

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
            start_new_session=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"openssl decryption failed (rc={result.returncode}): {result.stderr.strip()}"
            )

        with _tarfile.open(str(tar_path), "r:gz") as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if parts and len(parts) > 1 and parts[0] == "output":
                    member.name = str(Path(*parts[1:]))
                elif parts and parts[0] == "output":
                    continue
                tar.extract(member, path=str(output_dir), filter="data")

        logger.debug("At-rest decrypted %s → %s", enc_file, output_dir)
    finally:
        remove_files([path for path in (key_path, tar_path) if path is not None])
