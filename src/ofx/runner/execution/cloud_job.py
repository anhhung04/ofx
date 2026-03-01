"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
    RunResult,
)
from ofx.runner.execution.execution_results import (
    JobExecutionResult,
    StepExecutionResult,
)
from ofx.runner.execution.step import StepRunner
from ofx.runner.execution.error_helpers import job_step_failed
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class CloudJobRunner(BaseRunner[Job]):
    """Runs a job on a cloud VPS (or static remote host).

    Lifecycle:
        _pre_run:  resolve cloud config → provision/connect VPS → wait ready
        _do_run:   execute each step remotely via PostSSH/PostWinRM
        _post_run:  collect outputs → destroy VPS (if auto_destroy)
        _on_error:  cleanup on failure (destroy VPS to avoid cost leaks)
    """

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        cloud_config: CloudConfig | None = None,
    ):
        super().__init__(job, ctx, parent, parent.registry)
        self._cloud_config: CloudConfig = cloud_config or job.cloud  # type: ignore
        self._provider = None
        self._instance = None
        self._remote_runner = None  # PostSSH or PostWinRM
        self._work_dir: str | None = None

    # ------------------------------------------------------------------
    # Pre-run: provision + connect
    # ------------------------------------------------------------------

    async def _pre_run(self) -> None:
        from ofx.cloud.config import get_cloud_profile_manager

        # Resolve templates in job fields
        await self._resolve_template_fields(
            ["name", "needs", "run_if", "env", "defaults"]
        )
        from ofx.runner.context import RunnerContextBuilder
        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)

        # Resolve cloud profile
        cfg = self._cloud_config
        if isinstance(cfg, str):
            from ofx.models.cloud import parse_cloud_field
            cfg = parse_cloud_field(cfg)
        if cfg is None:
            raise RuntimeError("Cloud config is required for CloudJobRunner")

        mgr = get_cloud_profile_manager()
        resolved = mgr.resolve(cfg)
        self._cloud_config = resolved

        # Check run_if conditions (same as JobRunner)
        if isinstance(self.model.needs, str):
            self.model.needs = [self.model.needs]

        runners: dict[str, BaseRunner] = self.parent.runners  # type: ignore
        dep_runners = []
        for job_id in self.model.needs:
            runner = runners.get(job_id)
            if not runner:
                raise RuntimeError(
                    f"Job dependency '{job_id}' is missing from workflow runners."
                )
            dep_runners.append(runner)

        run_if_expr = self.model.run_if
        if run_if_expr is True and dep_runners:
            run_if_expr = "success()"

        if not self._evaluate_run_if(run_if_expr, self._run_if_context(dep_runners)):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise Exception(self._produce_log("Job condition is not met"))

        # Provision VPS or connect to static host
        self._log_info(
            f"Provisioning cloud instance for '{self.model.name or self.model.jid}' "
            f"(provider={resolved.provider})"
        )
        await self._provision_instance(resolved)

        # Store metadata in registry
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"steps", "env"}),
        )
        if self._instance:
            await self.reg_set("cloud_instance", {
                "instance_id": self._instance.instance_id,
                "ip": self._instance.ip,
                "provider": self._instance.provider,
                "region": self._instance.region,
            })

    async def _provision_instance(self, cfg: CloudConfig) -> None:
        """Create and connect to cloud instance."""
        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.ssh import wait_for_connectivity

        provider_name = cfg.provider or "static"
        provider_kwargs = self._build_provider_kwargs(cfg)
        self._provider = CloudProviderRegistry.create(provider_name, **provider_kwargs)

        # All provider methods are async — call them directly
        self._instance = await self._provider.create_instance(cfg)

        if provider_name != "static":
            # Wait for cloud instance to become ready
            self._log_info(
                f"Waiting for instance {self._instance.instance_id} to be ready..."
            )
            self._instance = await self._provider.wait_until_ready(
                self._instance.instance_id,
                timeout=cfg.startup_timeout or 300,
            )

            # Refresh IP (may be assigned after creation)
            refreshed = await self._provider.get_instance(self._instance.instance_id)
            if refreshed and refreshed.ip:
                self._instance = refreshed

        # Wait for SSH/WinRM connectivity
        if not self._instance or not self._instance.ip:
            raise RuntimeError("Instance has no IP address")

        is_windows = cfg.connection_type == "winrm"
        await wait_for_connectivity(
            host=self._instance.ip,
            connection_type="winrm" if is_windows else "ssh",
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=cfg.boot_timeout or 180,
        )

        # Create remote runner
        self._remote_runner = self._create_remote_runner(cfg)
        self._log_info(
            f"Connected to {self._instance.ip} via "
            f"{'WinRM' if is_windows else 'SSH'}"
        )

        # Setup working directory on remote
        if not is_windows:
            self._work_dir = f"/tmp/ofx-{self.run_id[:8]}"
            try:
                self._remote_runner.run(f"mkdir -p {self._work_dir}")
            except Exception:
                self._work_dir = "/tmp"
        else:
            self._work_dir = f"C:\\Windows\\Temp\\ofx-{self.run_id[:8]}"
            try:
                self._remote_runner.run(f'mkdir "{self._work_dir}" 2>nul')
            except Exception:
                self._work_dir = "C:\\Windows\\Temp"

    def _build_provider_kwargs(self, cfg: CloudConfig) -> dict[str, Any]:
        """Build kwargs for CloudProviderRegistry.create()."""
        kwargs: dict[str, Any] = {}
        provider = cfg.provider or "static"

        if provider == "static":
            kwargs["host"] = cfg.static_host or self._cloud_config.static_host
            kwargs["user"] = cfg.ssh_user
            kwargs["port"] = cfg.ssh_port or 22
            if cfg.ssh_key:
                kwargs["identity_file"] = cfg.ssh_key
            if cfg.ssh_password:
                kwargs["password"] = cfg.ssh_password
        elif provider == "digitalocean":
            token = cfg.extra.get("token") if cfg.extra else None
            if token:
                kwargs["token"] = token
        elif provider == "aws":
            for key in ("aws_access_key_id", "aws_secret_access_key", "region_name"):
                val = (cfg.extra or {}).get(key)
                if val:
                    kwargs[key] = val
            kwargs["region"] = cfg.region or "us-east-1"

        return kwargs

    def _create_remote_runner(self, cfg: CloudConfig):
        """Create PostSSH or PostWinRM instance for the provisioned instance."""
        from ofx.api.post import RunnerRegistry

        ip = self._instance.ip
        is_windows = cfg.connection_type == "winrm"

        if is_windows:
            return RunnerRegistry.create(
                "winrm",
                host=ip,
                username=cfg.winrm_user or "Administrator",
                password=cfg.winrm_password or cfg.ssh_password or "",
                ssl=cfg.winrm_ssl or False,
                port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
                opsec_mode=cfg.opsec_mode or False,
                log_commands=cfg.log_commands or False,
            )

        return RunnerRegistry.create(
            "ssh",
            host=ip,
            user=cfg.ssh_user or "root",
            port=cfg.ssh_port or 22,
            identity_file=cfg.ssh_key,
            password=cfg.ssh_password,
            use_controlmaster=True,
            opsec_mode=cfg.opsec_mode or False,
            log_commands=cfg.log_commands or False,
            max_retries=3,
        )

    # ------------------------------------------------------------------
    # Do-run: execute steps remotely
    # ------------------------------------------------------------------

    async def _do_run(self) -> None:
        self._log_info(
            f"Starting cloud job '{self.model.name or self.model.jid}' "
            f"on {self._instance.ip if self._instance else 'unknown'}"
        )

        for step in self.model.steps:
            step_ctx = self._child_context(
                update={
                    "secrets": self.ctx.secrets if step.secrets != "inherit" else {},
                },
            )

            # For cloud jobs, we use a CloudStepRunner that executes remotely
            step_runner = CloudStepRunner(
                step,
                step_ctx,
                self,
                remote_runner=self._remote_runner,
                work_dir=self._work_dir,
            )
            step_runner.log_level = logging.CRITICAL
            self._runners[str(step.step_index)] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    job_step_failed(step.name or step.step_index, result.error)
                )

    # ------------------------------------------------------------------
    # Post-run: collect outputs, destroy
    # ------------------------------------------------------------------

    async def _post_run(self) -> None:
        # Handle job outputs (same as JobRunner)
        if self.model.outputs:
            resolved_outputs = {}
            for key, value in self.model.outputs.items():
                resolved_value = await self._resolve_template(value)
                resolved_outputs[key] = resolved_value
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        # Build execution result
        step_results: list[dict[str, Any]] = []
        failed_steps: list[int] = []
        for runner in self._runners.values():
            if not isinstance(runner, (StepRunner, CloudStepRunner)):
                continue
            step_result = await runner.get_result()
            run_type = (
                runner._run_type.value
                if hasattr(runner, "_run_type")
                else runner.model.get_run_type().value
            )
            step_exec = StepExecutionResult(
                step_index=runner.model.step_index,
                name=runner.model.name,
                run_type=run_type,
                status=step_result.status.value,
                error=step_result.error,
                outputs=step_result.outputs,
            )
            step_results.append(step_exec.to_dict())
            if step_result.status == RunnerStatus.FAILED:
                failed_steps.append(runner.model.step_index)

        status_value = (
            RunnerStatus.COMPLETED.value
            if self.status == RunnerStatus.FINISHED
            else self.status.value
        )
        job_exec = JobExecutionResult(
            jid=self.model.jid,
            name=self.model.name,
            status=status_value,
            error=self._error,
            total_steps=len(self.model.steps),
            failed_steps=failed_steps,
            steps=step_results,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

        # Download outputs if output_path is set
        await self._download_outputs()

        # Destroy instance if auto_destroy
        await self._destroy_instance()

        # Cleanup remote runner
        self._cleanup_remote()

        self._log_debug(
            f"Cloud job '{self.model.name or self.model.jid}' result: "
            f"{await self.get_result()}"
        )

    async def _download_outputs(self) -> None:
        """Download output files from remote VPS."""
        if not self.ctx.output_path or not self._remote_runner:
            return

        is_windows = self._cloud_config.connection_type == "winrm"

        try:
            if is_windows:
                # List files in work dir
                files_output = self._remote_runner.run(
                    f'powershell "Get-ChildItem -Path \'{self._work_dir}\\output\' '
                    f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"'
                )
            else:
                files_output = self._remote_runner.run(
                    f"ls -1 {self._work_dir}/output 2>/dev/null || true"
                )

            files = [f.strip() for f in files_output.strip().split("\n") if f.strip()]
            if not files:
                return

            local_out = Path(self.ctx.output_path) / self.model.jid
            local_out.mkdir(parents=True, exist_ok=True)

            for fname in files:
                if is_windows:
                    remote = f"{self._work_dir}\\output\\{fname}"
                else:
                    remote = f"{self._work_dir}/output/{fname}"
                local = str(local_out / fname)
                try:
                    self._remote_runner.download(remote, local)
                except Exception as e:
                    self._log_debug(f"Failed to download {remote}: {e}")
        except Exception as e:
            self._log_debug(f"Output download failed: {e}")

    async def _destroy_instance(self) -> None:
        """Destroy cloud instance if auto_destroy is enabled."""
        cfg = self._cloud_config
        if not cfg or not getattr(cfg, "auto_destroy", True):
            return
        if not self._provider or not self._instance:
            return
        if (cfg.provider or "static") == "static":
            return  # Never destroy static hosts

        try:
            self._log_info(
                f"Destroying instance {self._instance.instance_id} "
                f"(provider={self._instance.provider})"
            )
            await self._provider.destroy_instance(self._instance.instance_id)
        except Exception as e:
            self._log_debug(f"Instance destroy failed: {e}")

    def _cleanup_remote(self) -> None:
        """Clean up remote runner resources."""
        if self._remote_runner and hasattr(self._remote_runner, "cleanup"):
            try:
                self._remote_runner.cleanup()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def _on_error(self, error: Exception) -> None:
        """Cleanup on error — destroy VPS to avoid cost leaks."""
        self._cleanup_remote()
        await self._destroy_instance()
        await super()._on_error(error)

    # ------------------------------------------------------------------
    # Helpers (same as JobRunner)
    # ------------------------------------------------------------------

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self.model.jid}' [cloud] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    def _run_if_context(self, dep_runners: list[BaseRunner]) -> dict[str, Any]:
        if not dep_runners:
            return {
                "success": lambda: True,
                "failure": lambda: False,
                "canceled": lambda: False,
                "always": lambda: True,
            }
        return {
            "success": lambda: all(r.is_success for r in dep_runners),
            "failure": lambda: any(r.is_failed for r in dep_runners),
            "canceled": lambda: any(
                r.status == RunnerStatus.CANCELED for r in dep_runners
            ),
            "always": lambda: True,
        }


class CloudStepRunner(BaseRunner):
    """Runs a step remotely via PostSSH or PostWinRM.

    Instead of using local subprocess (like the normal StepRunner),
    this sends commands to the remote host via the provided remote_runner.
    """

    def __init__(
        self,
        step,
        ctx: RunContext,
        parent: CloudJobRunner,
        remote_runner,
        work_dir: str | None = None,
    ):
        super().__init__(step, ctx, parent, parent.registry)
        self._remote = remote_runner
        self._work_dir = work_dir or "/tmp"
        self._run_type = None

    async def _pre_run(self) -> None:
        from ofx.models.step import RunType

        self._run_type = self.model.get_run_type()
        resolve_fields = [
            "name", "shell", "working_directory", "log_stdout",
            "env", "run_if",
        ]
        if self._run_type == RunType.COMMAND:
            resolve_fields.extend(["run"])
        elif self._run_type == RunType.SCRIPT:
            resolve_fields.extend(["script"])
        elif self._run_type == RunType.SCRIPT_FILE:
            resolve_fields.extend(["script_file"])

        await self._resolve_template_fields(resolve_fields)

        # Check run_if
        if self.model.run_if is not None and self.model.run_if is not True:
            if not self._evaluate_run_if(self.model.run_if, {}):
                self._state_machine.transition(RunnerStatus.CANCELED)
                raise Exception(self._produce_log("Step condition not met"))

    async def _do_run(self) -> None:
        from ofx.models.step import RunType

        run_type = self._run_type
        retry = self.model.retry or 0
        retry_delay = self.model.retry_delay or 5
        timeout_minutes = self.model.timeout
        timeout_secs = int(timeout_minutes * 60) if timeout_minutes else None

        last_error = None
        for attempt in range(retry + 1):
            try:
                if run_type == RunType.COMMAND:
                    output = await self._run_remote_command(
                        self.model.run, timeout=timeout_secs
                    )
                elif run_type == RunType.SCRIPT:
                    output = await self._run_remote_script(
                        self.model.script, timeout=timeout_secs
                    )
                elif run_type == RunType.SCRIPT_FILE:
                    output = await self._run_remote_script_file(
                        self.model.script_file, timeout=timeout_secs
                    )
                elif run_type == RunType.WORKFLOW:
                    # Reusable workflows not supported in cloud mode yet
                    raise RuntimeError(
                        "Reusable workflows ('uses') are not supported in cloud job mode"
                    )
                else:
                    raise RuntimeError(f"Unknown run type: {run_type}")

                # Store output
                if output:
                    await self.reg_set(RunnerRegistryKeys.OUTPUTS, {"stdout": output})

                # Log output
                if self.model.log_stdout and output and self.ctx.output_path:
                    self._save_output(output)

                return  # Success

            except Exception as e:
                last_error = e
                if attempt < retry:
                    self._log_debug(
                        f"Step failed (attempt {attempt + 1}/{retry + 1}), "
                        f"retrying in {retry_delay}s: {e}"
                    )
                    await asyncio.sleep(retry_delay)

        raise RuntimeError(f"Step failed after {retry + 1} attempts: {last_error}")

    async def _post_run(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Remote execution methods
    # ------------------------------------------------------------------

    async def _run_remote_command(self, command: str, timeout: int | None = None) -> str:
        """Run a shell command on the remote host."""
        # Build environment prefix
        env_prefix = self._build_env_prefix()
        work_dir = self.model.working_directory or self._work_dir

        full_cmd = ""
        if env_prefix:
            full_cmd += env_prefix + " "
        full_cmd += f"cd {work_dir} 2>/dev/null; {command}"

        return await asyncio.to_thread(
            self._remote.run, full_cmd, timeout
        )

    async def _run_remote_script(self, script: str, timeout: int | None = None) -> str:
        """Run an inline script on the remote host."""
        import secrets as _secrets

        remote_script = f"{self._work_dir}/.ofx_script_{_secrets.token_hex(4)}.sh"

        # Upload script content
        local_tmp = tempfile.mktemp(prefix="ofx_script_", suffix=".sh")
        try:
            Path(local_tmp).write_text(f"#!/bin/bash\n{script}\n")
            await asyncio.to_thread(self._remote.upload, local_tmp, remote_script)
        finally:
            Path(local_tmp).unlink(missing_ok=True)

        # Execute
        try:
            env_prefix = self._build_env_prefix()
            work_dir = self.model.working_directory or self._work_dir
            full_cmd = f"chmod +x {remote_script} && cd {work_dir} 2>/dev/null && "
            if env_prefix:
                full_cmd += env_prefix + " "
            full_cmd += remote_script
            return await asyncio.to_thread(self._remote.run, full_cmd, timeout)
        finally:
            # Cleanup remote script
            try:
                await asyncio.to_thread(
                    self._remote.run, f"rm -f {remote_script}", 10
                )
            except Exception:
                pass

    async def _run_remote_script_file(
        self, script_file: str, timeout: int | None = None
    ) -> str:
        """Upload and run a local script file on the remote host."""
        local_path = str(Path(script_file).expanduser().resolve())
        if not Path(local_path).exists():
            raise FileNotFoundError(f"Script file not found: {local_path}")

        remote_script = f"{self._work_dir}/{Path(local_path).name}"
        await asyncio.to_thread(self._remote.upload, local_path, remote_script)

        try:
            env_prefix = self._build_env_prefix()
            work_dir = self.model.working_directory or self._work_dir
            full_cmd = f"chmod +x {remote_script} && cd {work_dir} 2>/dev/null && "
            if env_prefix:
                full_cmd += env_prefix + " "
            full_cmd += remote_script
            return await asyncio.to_thread(self._remote.run, full_cmd, timeout)
        finally:
            try:
                await asyncio.to_thread(
                    self._remote.run, f"rm -f {remote_script}", 10
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_env_prefix(self) -> str:
        """Build environment variable export prefix for remote command."""
        env_vars = {}
        # Merge context envs + step envs
        env_vars.update(self.ctx.envs or {})
        if hasattr(self.model, "env") and self.model.env:
            env_vars.update(self.model.env)

        if not env_vars:
            return ""

        exports = " ".join(
            f'{k}="{v}"' for k, v in env_vars.items()
            if k not in ("PATH", "HOME", "USER", "SHELL")
        )
        return f"export {exports} &&" if exports else ""

    def _save_output(self, output: str) -> None:
        """Save step output to local file."""
        if not self.ctx.output_path:
            return
        out_dir = Path(self.ctx.output_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        step_name = self.model.name or f"step_{self.model.step_index}"
        out_file = out_dir / f"{step_name}.log"
        out_file.write_text(output)

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"step[{self.model.step_index}] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
