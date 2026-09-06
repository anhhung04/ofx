"""Session submission: local background processes and cloud VPS provisioning."""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.models import Session, SessionStatus
from ofx.cloud.sessions.python_steps import (
    iter_python_step_bundles as _iter_python_step_bundles,
)
from ofx.cloud.sessions.script_builder import build_session_script
from ofx.cloud.temp_upload import upload_temp_content

logger = logging.getLogger("ofx")

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

class SubmitMixin:
    @staticmethod
    def _session_at_rest_update(at_rest_key: str) -> dict[str, Any]:
        return {
            "at_rest_key": at_rest_key,
            "at_rest_encrypted": True,
        }
    @classmethod
    def _running_session_update(
        cls,
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
            **cls._session_at_rest_update(at_rest_key),
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
