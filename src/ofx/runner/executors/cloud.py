"""Executors for cloud job runners."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import shlex
from pathlib import Path
from typing import Any

from pathlib import PurePosixPath, PureWindowsPath

from ofx.cloud.runtime import is_windows_config, remote_join
from ofx.models.cloud import CloudConfig
from ofx.runner.context import context_copy, context_with_vars
from ofx.runner.executors.job import JobExecutor
from ofx.runner.executors.step import StepExecutor
from ofx.runner.handlers import HandlerRegistry
from ofx.runner.handlers import registry as default_handler_registry
from ofx.runner.services.cloud_provisioner import CloudProvisioner
from ofx.utils.log import register_secrets

@dataclass(frozen=True)
class _CloudInstanceState:
    provider: Any | None
    instance: Any | None
    provider_name: str
    instance_id: str
    instance_name: str
    instance_ip: str
    auto_destroy_enabled: bool
    has_destroyable_instance: bool
    has_reportable_instance: bool

class CloudExecutor(JobExecutor):
    """Cloud-specific executor helpers composed into cloud runners.

    This keeps cloud provisioning, remote dispatch setup, and instance cleanup
    separate from the runner lifecycle while preserving the current behavior of
    cloud runners.
    """

    def __init__(
        self,
        *,
        step_executor: StepExecutor | None = None,
        handler_registry: HandlerRegistry | None = None,
        provisioner: CloudProvisioner | None = None,
    ) -> None:
        self._step_executor = step_executor or StepExecutor()
        self._handler_registry = handler_registry or default_handler_registry
        self._provisioner = provisioner

    async def pre_run(self, runner) -> None:
        from ofx.cloud.config import get_cloud_profile_manager
        from ofx.models.cloud import parse_cloud_field

        await self._prepare_job_context(runner)
        cloud_config = (
            parse_cloud_field(runner._cloud_config)
            if isinstance(runner._cloud_config, str)
            else runner._cloud_config
        )
        resolved = (
            get_cloud_profile_manager().resolve(cloud_config)
            if cloud_config is not None
            else None
        )
        if resolved is None:
            raise RuntimeError(
                f"Cloud config is required for job '{runner.model.jid}'. "
                "Set 'cloud:' on the job or use a cloud profile."
            )
        runner._cloud_config = resolved
        credential_values = [
            value
            for value in (
                getattr(resolved, "ssh_password", None),
                getattr(resolved, "winrm_password", None),
                (resolved.extra or {}).get("token"),
                (resolved.extra or {}).get("aws_secret_access_key"),
            )
            if value
        ]
        register_secrets(credential_values)

        self.check_dependencies_and_run_if(runner)
        runner._log_info(
            f"Provisioning cloud instance for '{runner.model.name or runner.model.jid}' "
            f"(provider={resolved.provider})"
        )
        try:
            await self.provision_instance(runner, resolved)
        except Exception:
            await self.emergency_deprovision(runner)
            raise

        await self._store_job_model(runner)
        if runner._instance:
            await runner.reg_set(
                "cloud_instance",
                {
                    "instance_id": runner._instance.instance_id,
                    "ip": runner._instance.ip,
                    "provider": runner._instance.provider,
                    "region": runner._instance.region,
                },
            )

    async def do_run(self, runner) -> None:
        runner._log_info(
            f"Starting cloud job '{runner.model.name or runner.model.jid}' "
            f"on {runner._instance.ip if runner._instance else 'unknown'}"
        )
        await runner._upload_fleet_input()
        await self.dispatch_remote_steps(runner, None)

    async def post_run(self, runner) -> None:
        await self.save_job_results(runner)
        await self.download_outputs(runner)
        await self.destroy_instance(runner)
        await self.cleanup_remote(runner)

    async def on_failure(self, runner) -> None:
        try:
            await self.download_outputs(runner)
        except Exception as exc:
            runner._log_warning(f"Output salvage on failure failed: {exc}")
        await self.destroy_instance(runner)
        await self.cleanup_remote(runner)

    async def provision_instance(self, runner, cfg: CloudConfig) -> None:
        from ofx.cloud import CloudProviderRegistry

        provisioner = self._provisioner or CloudProvisioner(CloudProviderRegistry)
        provider, instance, remote_runner, work_dir = await provisioner.provision(cfg)
        is_windows = bool(cfg and is_windows_config(cfg))

        runner._provider = provider
        runner._instance = instance
        runner._remote_runner = remote_runner
        runner._work_dir = work_dir
        runner._log_info(
            f"Connected to {runner._instance.ip} via "
            f"{'WinRM' if is_windows else 'SSH'}"
        )

        try:
            work_dir_command = (
                f'mkdir "{runner._work_dir}" 2>nul'
                if is_windows
                else f"mkdir -p {shlex.quote(runner._work_dir)}"
            )
            await asyncio.to_thread(
                runner._remote_runner.run,
                work_dir_command,
            )
        except Exception as exc:
            fallback_work_dir = "C:\\Windows\\Temp" if is_windows else "/tmp"
            fallback_label = "Temp" if is_windows else "/tmp"
            runner._log_warning(
                f"Work dir creation failed, using {fallback_label}: {exc}"
            )
            runner._work_dir = fallback_work_dir

    async def destroy_instance(self, runner) -> None:
        state = self._cloud_instance_state(runner)
        if not state.has_destroyable_instance or not state.auto_destroy_enabled:
            return

        try:
            runner._log_info(
                f"Destroying instance '{state.instance_name}'"
                f"[{state.instance_id}] "
                f"(provider={state.provider_name})"
            )
            if self._provisioner is None:
                await state.provider.destroy_instance(state.instance_id)
            else:
                await self._provisioner.destroy(state.provider, state.instance)
        except Exception as exc:
            runner._log_warning(f"Instance destroy failed: {exc}")

    async def emergency_deprovision(self, runner) -> None:
        state = self._cloud_instance_state(runner)
        if state.has_destroyable_instance:
            try:
                runner._log_warning(
                    "Emergency cleanup: destroying partially-provisioned "
                    f"instance {state.instance_id}"
                )
                if self._provisioner is None:
                    await state.provider.destroy_instance(state.instance_id)
                else:
                    await self._provisioner.destroy(state.provider, state.instance)
            except Exception as exc:
                runner._log_warning(
                    "Emergency instance destroy failed (may require manual cleanup): "
                    f"{exc}"
                )
        await self.cleanup_remote(runner)

    @staticmethod
    def _cloud_instance_state(runner) -> _CloudInstanceState:
        instance = getattr(runner, "_instance", None)
        cfg = getattr(runner, "_cloud_config", None)
        instance_provider = getattr(instance, "provider", None) if instance else None
        return _CloudInstanceState(
            provider=getattr(runner, "_provider", None),
            instance=instance,
            provider_name=instance_provider or getattr(cfg, "provider", None) or "static",
            instance_id=(getattr(instance, "instance_id", None) or "unknown") if instance else "unknown",
            instance_name=(getattr(instance, "name", None) or "unknown") if instance else "unknown",
            instance_ip=(getattr(instance, "ip", None) or "") if instance else "",
            auto_destroy_enabled=bool(cfg and getattr(cfg, "auto_destroy", True)),
            has_destroyable_instance=bool(
                getattr(runner, "_provider", None)
                and instance
                and (instance_provider or getattr(cfg, "provider", None) or "static") != "static"
            ),
            has_reportable_instance=bool(
                instance
                and (getattr(instance, "ip", None) or "")
                and (instance_provider or getattr(cfg, "provider", None) or "static") != "static"
            ),
        )

    async def cleanup_remote(self, runner) -> None:
        remote_runner = getattr(runner, "_remote_runner", None)
        if remote_runner is None:
            return
        work_dir = getattr(runner, "_work_dir", None)
        cloud_config = getattr(runner, "_cloud_config", None)
        is_windows = bool(cloud_config and is_windows_config(cloud_config))

        if work_dir and work_dir not in ("/tmp", "C:\\Windows\\Temp"):
            try:
                cleanup_command = (
                    "powershell \"Remove-Item -Path "
                    f"'{work_dir}' -Recurse -Force -ErrorAction SilentlyContinue\""
                    if is_windows
                    else f"rm -rf {shlex.quote(work_dir)}"
                )
                await asyncio.to_thread(
                    remote_runner.run,
                    cleanup_command,
                    15,
                )
            except Exception as exc:
                runner._log_debug(f"Failed to clean remote work dir: {exc}")

        if not hasattr(remote_runner, "cleanup"):
            return

        try:
            await asyncio.to_thread(remote_runner.cleanup)
        except Exception as exc:
            runner._log_debug(f"Remote runner cleanup failed: {exc}")

    async def dispatch_remote_steps(
        self,
        runner,
        matrix_combo: dict[str, Any] | None,
        suffix: str = "",
    ) -> None:
        loop_ctx = context_copy(runner.ctx)
        if matrix_combo:
            merged_matrix = dict(loop_ctx.vars.get("matrix", {}))
            merged_matrix.update(matrix_combo)
            loop_ctx = context_with_vars(loop_ctx, {"matrix": merged_matrix})

        await self._execute_steps(runner, suffix=suffix, loop_ctx=loop_ctx)

    def _create_step_runner(self, runner, step, step_ctx):
        from ofx.runner.cloud_step import CloudStepRunner

        return CloudStepRunner(
            step,
            step_ctx,
            runner,
            remote_runner=runner._remote_runner,
            work_dir=runner._work_dir,
            executor=self._step_executor,
            handler_registry=self._handler_registry,
        )

    async def download_outputs(self, runner) -> None:
        remote_runner = getattr(runner, "_remote_runner", None)
        output_path = getattr(getattr(runner, "ctx", None), "output_path", None)
        if remote_runner is None or not output_path:
            return
        work_dir = getattr(runner, "_work_dir", None)
        if work_dir is None:
            return
        cloud_config = getattr(runner, "_cloud_config", None)
        is_windows = bool(cloud_config and is_windows_config(cloud_config))
        job_id = getattr(getattr(runner, "model", None), "jid", None)
        if not job_id:
            return

        try:
            list_output_files_command = (
                "powershell \"Get-ChildItem -Path '"
                f"{remote_join(work_dir, 'output', is_windows=is_windows)}' -File -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty Name\""
                if is_windows
                else f"ls -1 {shlex.quote(remote_join(work_dir, 'output', is_windows=is_windows))} 2>/dev/null || true"
            )
            files_output = await asyncio.to_thread(
                remote_runner.run,
                list_output_files_command,
            )
            files = [line.strip() for line in files_output.strip().splitlines() if line.strip()]
            if not files:
                return

            local_out = Path(output_path) / job_id
            local_out.mkdir(parents=True, exist_ok=True)
            for filename in files:
                safe_name = (PureWindowsPath if is_windows else PurePosixPath)(filename).name
                if not safe_name or safe_name in (".", ".."):
                    continue

                remote = remote_join(
                    work_dir,
                    "output",
                    safe_name,
                    is_windows=is_windows,
                )
                local = str(local_out / safe_name)
                try:
                    await asyncio.to_thread(
                        remote_runner.download,
                        remote,
                        local,
                    )
                except Exception as exc:
                    runner._log_debug(f"Failed to download {remote}: {exc}")
        except Exception as exc:
            runner._log_debug(f"Output download failed: {exc}")
