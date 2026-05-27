"""Executors for cloud job runners."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.runner.executors.job import JobExecutor
from ofx.utils.tempfiles import remote_work_dir


class CloudExecutor(JobExecutor):
    """Cloud-specific executor helpers composed into cloud runners.

    This keeps cloud provisioning, remote dispatch setup, and instance cleanup
    separate from the runner lifecycle while preserving the current behavior of
    ``CloudJobRunner``.
    """

    async def provision_instance(self, runner, cfg: CloudConfig) -> None:
        """Create and connect to a cloud instance for the given runner."""
        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.ssh import wait_for_connectivity, wait_for_login

        provider_name = cfg.provider or "static"
        provider_kwargs = runner._build_provider_kwargs(cfg)
        runner._provider = CloudProviderRegistry.create(provider_name, **provider_kwargs)

        runner._instance = await runner._provider.create_instance(cfg)

        if provider_name != "static":
            runner._log_info(
                f"Waiting for instance '{runner._instance.name}'[{runner._instance.instance_id}] to be ready..."
            )
            runner._instance = await runner._provider.wait_until_ready(
                runner._instance.instance_id,
                timeout=cfg.startup_timeout or 300,
            )

            refreshed = await runner._provider.get_instance(runner._instance.instance_id)
            if refreshed and refreshed.ip:
                runner._instance = refreshed

        if not runner._instance or not runner._instance.ip:
            iid = runner._instance.instance_id if runner._instance else "none"
            raise RuntimeError(
                "Cloud instance has no IP address after provisioning.\n"
                f"  Job: {runner.model.jid}\n"
                f"  Provider: {cfg.provider}\n"
                f"  Instance ID: {iid}\n"
                "Check cloud provider dashboard for instance status, "
                "verify networking config, and retry."
            )

        is_windows = cfg.connection_type == "winrm"
        runner._log_info(
            f"Waiting for connectivity to {runner._instance.ip} "
            f"on {'WinRM' if is_windows else 'SSH'}..."
        )
        await wait_for_connectivity(
            host=runner._instance.ip,
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=cfg.boot_timeout or 180,
            os_type="windows" if is_windows else "linux",
        )
        runner._log_info(
            f"Instance {runner._instance.ip} is reachable. Waiting for SSH service..."
        )
        await wait_for_login(
            host=runner._instance.ip,
            cfg=cfg,
            timeout=cfg.login_timeout,
        )

        runner._remote_runner = runner._create_remote_runner(cfg)
        runner._log_info(
            f"Connected to {runner._instance.ip} via {'WinRM' if is_windows else 'SSH'}"
        )

        if not is_windows:
            runner._work_dir = remote_work_dir(runner.run_id)
            try:
                await asyncio.to_thread(
                    runner._remote_runner.run,
                    f"mkdir -p {shlex.quote(runner._work_dir)}",
                )
            except Exception as exc:
                runner._log_warning(f"Work dir creation failed, using /tmp: {exc}")
                runner._work_dir = "/tmp"
        else:
            runner._work_dir = remote_work_dir(runner.run_id, is_windows=True)
            try:
                await asyncio.to_thread(
                    runner._remote_runner.run,
                    f'mkdir "{runner._work_dir}" 2>nul',
                )
            except Exception as exc:
                runner._log_warning(f"Work dir creation failed, using Temp: {exc}")
                runner._work_dir = "C:\\Windows\\Temp"

    async def destroy_instance(self, runner) -> None:
        """Destroy the cloud instance when auto-destroy is enabled."""
        cfg = runner._cloud_config
        if not cfg or not getattr(cfg, "auto_destroy", True):
            return
        if not runner._provider or not runner._instance:
            return
        if (cfg.provider or "static") == "static":
            return

        try:
            runner._log_info(
                f"Destroying instance '{runner._instance.name}'[{runner._instance.instance_id}] "
                f"(provider={runner._instance.provider})"
            )
            await runner._provider.destroy_instance(runner._instance.instance_id)
        except Exception as exc:
            runner._log_warning(f"Instance destroy failed: {exc}")

    async def emergency_deprovision(self, runner) -> None:
        """Best-effort cleanup for partially provisioned instances."""
        if runner._provider and runner._instance:
            is_static = (
                runner._cloud_config
                and (runner._cloud_config.provider or "static") == "static"
            )
            if not is_static:
                try:
                    runner._log_warning(
                        "Emergency cleanup: destroying partially-provisioned "
                        f"instance {runner._instance.instance_id}"
                    )
                    await runner._provider.destroy_instance(runner._instance.instance_id)
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

    async def cleanup_remote(self, runner) -> None:
        """Clean up remote work dir and transport resources."""
        if not runner._remote_runner:
            return

        if runner._work_dir and runner._work_dir not in ("/tmp", "C:\\Windows\\Temp"):
            try:
                is_windows = (
                    runner._cloud_config
                    and runner._cloud_config.connection_type == "winrm"
                )
                if is_windows:
                    await asyncio.to_thread(
                        runner._remote_runner.run,
                        f"powershell \"Remove-Item -Path '{runner._work_dir}' -Recurse -Force -ErrorAction SilentlyContinue\"",
                        15,
                    )
                else:
                    await asyncio.to_thread(
                        runner._remote_runner.run,
                        f"rm -rf {shlex.quote(runner._work_dir)}",
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
        """Run all steps remotely through ``CloudStepRunner``."""
        from ofx.runner.execution.cloud_step import CloudStepRunner
        from ofx.runner.execution.error_helpers import job_step_failed

        loop_ctx = runner._child_context()
        if matrix_combo:
            if "matrix" not in loop_ctx.vars:
                loop_ctx.vars["matrix"] = {}
            loop_ctx.vars["matrix"].update(matrix_combo)

        for step in runner.model.steps:
            step_ctx = loop_ctx.model_copy(deep=True)
            if step.secrets != "inherit":
                step_ctx.secrets = {}

            step_runner = CloudStepRunner(
                step,
                step_ctx,
                runner,
                remote_runner=runner._remote_runner,
                work_dir=runner._work_dir,
            )
            runner_key = f"{step.step_index}{suffix}"
            runner._runners[runner_key] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    job_step_failed(step.name or step.step_index, result.error)
                )

    async def download_outputs(self, runner) -> None:
        """Download output files from the remote host."""
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
        """Create the transport used for remote command execution."""
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
