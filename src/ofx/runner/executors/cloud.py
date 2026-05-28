"""Executors for cloud job runners."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.executors.job import JobExecutor
from ofx.runner.executors.step import StepExecutor
from ofx.runner.handlers import HandlerRegistry
from ofx.runner.handlers import registry as default_handler_registry
from ofx.runner.services.cloud_provisioner import CloudProvisioner


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

    @staticmethod
    def _is_windows_connection(cfg: CloudConfig | None) -> bool:
        return bool(cfg and cfg.connection_type == "winrm")

    @classmethod
    def _create_work_dir_command(cls, cfg: CloudConfig | None, work_dir: str) -> str:
        if cls._is_windows_connection(cfg):
            return f'mkdir "{work_dir}" 2>nul'
        return f"mkdir -p {shlex.quote(work_dir)}"

    @classmethod
    def _cleanup_work_dir_command(cls, cfg: CloudConfig | None, work_dir: str) -> str:
        if cls._is_windows_connection(cfg):
            return (
                "powershell \"Remove-Item -Path "
                f"'{work_dir}' -Recurse -Force -ErrorAction SilentlyContinue\""
            )
        return f"rm -rf {shlex.quote(work_dir)}"

    @classmethod
    def _fallback_work_dir(cls, cfg: CloudConfig | None) -> str:
        if cls._is_windows_connection(cfg):
            return "C:\\Windows\\Temp"
        return "/tmp"

    @classmethod
    def _fallback_work_dir_label(cls, cfg: CloudConfig | None) -> str:
        return "Temp" if cls._is_windows_connection(cfg) else "/tmp"

    async def pre_run(self, runner) -> None:
        from ofx.cloud.config import get_cloud_profile_manager
        from ofx.runner.services.secret_redactor import SecretRedactor

        await self._prepare_job_context(runner)

        cfg = runner._cloud_config
        if isinstance(cfg, str):
            from ofx.models.cloud import parse_cloud_field

            cfg = parse_cloud_field(cfg)
        if cfg is None:
            raise RuntimeError(
                f"Cloud config is required for job '{runner.model.jid}'. "
                "Set 'cloud:' on the job or use a cloud profile."
            )

        resolved = get_cloud_profile_manager().resolve(cfg)
        runner._cloud_config = resolved

        cred_vals: list[str] = []
        for attr in ("ssh_password", "winrm_password"):
            value = getattr(resolved, attr, None)
            if value:
                cred_vals.append(value)
        if resolved.extra:
            for key in ("token", "aws_secret_access_key"):
                value = resolved.extra.get(key)
                if value:
                    cred_vals.append(value)
        SecretRedactor.register(cred_vals)

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

        runner._provider = provider
        runner._instance = instance
        runner._remote_runner = remote_runner
        runner._work_dir = work_dir

        runner._log_info(
            f"Connected to {runner._instance.ip} via {'WinRM' if self._is_windows_connection(cfg) else 'SSH'}"
        )

        try:
            await asyncio.to_thread(
                runner._remote_runner.run,
                self._create_work_dir_command(cfg, runner._work_dir),
            )
        except Exception as exc:
            runner._log_warning(
                f"Work dir creation failed, using {self._fallback_work_dir_label(cfg)}: {exc}"
            )
            runner._work_dir = self._fallback_work_dir(cfg)

    async def destroy_instance(self, runner) -> None:
        cfg = runner._cloud_config
        if not cfg or not getattr(cfg, "auto_destroy", True):
            return
        if not runner._provider or not runner._instance:
            return
        if self._is_static_provider(runner):
            return

        try:
            runner._log_info(
                f"Destroying instance '{runner._instance.name}'[{runner._instance.instance_id}] "
                f"(provider={runner._instance.provider})"
            )
            await self._destroy_current_instance(runner)
        except Exception as exc:
            runner._log_warning(f"Instance destroy failed: {exc}")

    async def emergency_deprovision(self, runner) -> None:
        if runner._provider and runner._instance:
            if not self._is_static_provider(runner):
                try:
                    runner._log_warning(
                        "Emergency cleanup: destroying partially-provisioned "
                        f"instance {runner._instance.instance_id}"
                    )
                    await self._destroy_current_instance(runner)
                except Exception as exc:
                    runner._log_warning(
                        "Emergency instance destroy failed "
                        f"(may require manual cleanup): {exc}"
                    )
        if runner._remote_runner and hasattr(runner._remote_runner, "cleanup"):
            try:
                await asyncio.to_thread(runner._remote_runner.cleanup)
            except Exception as exc:
                runner._log_debug(f"Remote runner cleanup failed: {exc}")

    def _is_static_provider(self, runner) -> bool:
        cfg = runner._cloud_config
        return bool(cfg and (cfg.provider or "static") == "static")

    async def _destroy_current_instance(self, runner) -> None:
        provisioner = self._provisioner
        if provisioner is None:
            await runner._provider.destroy_instance(runner._instance.instance_id)
        else:
            await provisioner.destroy(runner._provider, runner._instance)

    async def cleanup_remote(self, runner) -> None:
        if not runner._remote_runner:
            return

        if runner._work_dir and runner._work_dir not in ("/tmp", "C:\\Windows\\Temp"):
            try:
                await asyncio.to_thread(
                    runner._remote_runner.run,
                    self._cleanup_work_dir_command(runner._cloud_config, runner._work_dir),
                    15,
                )
            except Exception as exc:
                runner._log_debug(f"Failed to clean remote work dir: {exc}")

        if hasattr(runner._remote_runner, "cleanup"):
            try:
                await asyncio.to_thread(runner._remote_runner.cleanup)
            except Exception as exc:
                runner._log_debug(f"Remote runner cleanup failed: {exc}")

    async def dispatch_remote_steps(
        self,
        runner,
        matrix_combo: dict[str, Any] | None,
        suffix: str = "",
    ) -> None:
        from ofx.runner.cloud_step import CloudStepRunner
        from ofx.runner.error_helpers import job_step_failed

        loop_ctx = runner._child_context()
        if matrix_combo:
            merged_matrix = dict(loop_ctx.vars.get("matrix", {}))
            merged_matrix.update(matrix_combo)
            loop_ctx = RunnerContextBuilder(loop_ctx).with_vars(
                {"matrix": merged_matrix}
            )

        for step in runner.model.steps:
            step_ctx = loop_ctx.model_copy(deep=True)
            if step.secrets != "inherit":
                step_ctx = RunnerContextBuilder(step_ctx).with_update({"secrets": {}})

            step_runner = CloudStepRunner(
                step,
                step_ctx,
                runner,
                remote_runner=runner._remote_runner,
                work_dir=runner._work_dir,
                executor=self._step_executor,
                handler_registry=self._handler_registry,
            )
            runner_key = f"{step.step_index}{suffix}"
            runner._runners[runner_key] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(job_step_failed(step.name or step.step_index, result.error))

    async def download_outputs(self, runner) -> None:
        from pathlib import PurePosixPath, PureWindowsPath

        if not runner.ctx.output_path or not runner._remote_runner:
            return

        is_windows = runner._cloud_config.connection_type == "winrm"
        assert runner._work_dir is not None, "_work_dir must be set before fetching outputs"

        try:
            if is_windows:
                files_output = await asyncio.to_thread(
                    runner._remote_runner.run,
                    f"powershell \"Get-ChildItem -Path '{runner._work_dir}\\output' "
                    f"-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name\"",
                )
            else:
                files_output = await asyncio.to_thread(
                    runner._remote_runner.run,
                    f"ls -1 {shlex.quote(runner._work_dir + '/output')} 2>/dev/null || true",
                )

            files = [f.strip() for f in files_output.strip().splitlines() if f.strip()]
            if not files:
                return

            local_out = Path(runner.ctx.output_path) / runner.model.jid
            local_out.mkdir(parents=True, exist_ok=True)

            for fname in files:
                safe_name = (
                    PureWindowsPath(fname).name
                    if is_windows
                    else PurePosixPath(fname).name
                )
                if not safe_name or safe_name in (".", ".."):
                    continue
                if is_windows:
                    remote = f"{runner._work_dir}\\output\\{safe_name}"
                else:
                    remote = f"{runner._work_dir}/output/{safe_name}"
                local = str(local_out / safe_name)
                try:
                    await asyncio.to_thread(runner._remote_runner.download, remote, local)
                except Exception as exc:
                    runner._log_debug(f"Failed to download {remote}: {exc}")
        except Exception as exc:
            runner._log_debug(f"Output download failed: {exc}")

    def build_remote_runner(self, runner, cfg: CloudConfig):
        from ofx.cloud.runtime import create_remote_runner
        from ofx.utils.tempfiles import make_temp_file

        if not runner._instance:
            raise RuntimeError(
                f"Cloud job '{runner.model.jid}' cannot proceed: no instance provisioned.\n"
                "This typically means instance provisioning failed earlier. "
                "Check logs above for provisioning errors."
            )

        ip = runner._instance.ip
        is_log_commands = cfg.log_commands or False
        log_path = None
        if is_log_commands:
            if runner.ctx.output_path:
                log_dir = Path(runner.ctx.output_path) / "logs" / "cloud_commands"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"{runner.model.jid}_{ip}.log"
            else:
                log_path = make_temp_file(prefix=".tmp_rcmd_", suffix=".log")
            runner._log_info(
                f"Command logging enabled. Logs will be saved to: {log_path}"
            )

        return create_remote_runner(
            cfg,
            ip,
            log_path=str(log_path) if log_path else None,
            max_retries=3,
        )
