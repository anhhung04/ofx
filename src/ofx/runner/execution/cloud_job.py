"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
import os
import sys
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
)
from ofx.runner.execution.cloud_step import CloudStepRunner
from ofx.runner.execution.error_helpers import job_step_failed
from ofx.runner.execution.execution_results import (
    build_job_execution_result,
    build_run_if_context,
)

# logger will be injected via CloudJobRunner instance


async def _prompt_destroy_instance(instance_info: str) -> bool:
    """Ask the user whether to destroy a cloud instance.

    Returns True if the user confirms destruction.  Falls back to *not*
    destroying when stdin is not a TTY (e.g. session / CI mode).
    """
    if not sys.stdin.isatty():
        return False
    try:
        answer = await asyncio.to_thread(
            input,
            f"\n⚠  Cloud instance still running: {instance_info}\n"
            "   Destroy this instance? [y/N]: ",
        )
        return answer.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


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
        self._is_fleet_child: bool = False  # Set by CloudFleetRunner for fleet children
        self._cached_python: str | None = None  # Cached across steps on same VPS

    async def run(self, *args, **kwargs):
        """Override to salvage outputs and prompt before VPS destruction on failure."""
        result = await super().run(*args, **kwargs)
        if result.status == RunnerStatus.FAILED:
            # Fleet children defer the destroy prompt to CloudMatrixJobRunner,
            # which handles all surviving instances in a single batch.
            await self._handle_failure(prompt_destroy=not self._is_fleet_child)
        return result

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

        # Register cloud credential values for log redaction using SecretRedactor.
        from ofx.runner.services.secret_redactor import SecretRedactor

        _cred_vals = []
        for attr in ("ssh_password", "winrm_password"):
            v = getattr(resolved, attr, None)
            if v:
                _cred_vals.append(v)
        if resolved.extra:
            for k in ("token", "aws_secret_access_key"):
                v = resolved.extra.get(k)
                if v:
                    _cred_vals.append(v)
        # Register collected secrets (duplicates are ignored by the service).
        SecretRedactor.register(_cred_vals)

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

        if not self._evaluate_run_if(run_if_expr, build_run_if_context(dep_runners)):
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
            await self.reg_set(
                "cloud_instance",
                {
                    "instance_id": self._instance.instance_id,
                    "ip": self._instance.ip,
                    "provider": self._instance.provider,
                    "region": self._instance.region,
                },
            )

    async def _provision_instance(self, cfg: CloudConfig) -> None:
        """Create and connect to cloud instance."""
        from ofx.cloud import CloudProviderRegistry
        from ofx.cloud.ssh import wait_for_connectivity, wait_for_login

        provider_name = cfg.provider or "static"
        provider_kwargs = self._build_provider_kwargs(cfg)
        self._provider = CloudProviderRegistry.create(provider_name, **provider_kwargs)

        self._instance = await self._provider.create_instance(cfg)

        if provider_name != "static":
            self._log_info(
                f"Waiting for instance '{self._instance.name}'[{self._instance.instance_id}] to be ready..."
            )
            self._instance = await self._provider.wait_until_ready(
                self._instance.instance_id,
                timeout=cfg.startup_timeout or 300,
            )

            # Refresh IP (may be assigned after creation)
            refreshed = await self._provider.get_instance(self._instance.instance_id)
            if refreshed and refreshed.ip:
                self._instance = refreshed

        if not self._instance or not self._instance.ip:
            raise RuntimeError("Instance has no IP address")

        is_windows = cfg.connection_type == "winrm"
        self._log_info(
            f"Waiting for connectivity to {self._instance.ip} "
            f"on {'WinRM' if is_windows else 'SSH'}..."
        )
        await wait_for_connectivity(
            host=self._instance.ip,
            ssh_port=cfg.ssh_port or 22,
            winrm_port=cfg.winrm_port or (5986 if cfg.winrm_ssl else 5985),
            timeout=cfg.boot_timeout or 180,
            os_type="windows" if is_windows else "linux",
        )
        self._log_info(
            f"Instance {self._instance.ip} is reachable. Waiting for SSH service..."
        )
        await wait_for_login(
            host=self._instance.ip,
            cfg=cfg,
            timeout=cfg.login_timeout,
        )
        # Create remote runner
        self._remote_runner = self._create_remote_runner(cfg)
        self._log_info(
            f"Connected to {self._instance.ip} via {'WinRM' if is_windows else 'SSH'}"
        )

        # Setup working directory on remote
        if not is_windows:
            self._work_dir = f"/tmp/.run-{self.run_id[:8]}"
            try:
                await asyncio.to_thread(
                    self._remote_runner.run, f"mkdir -p {self._work_dir}"
                )
            except Exception:
                self._work_dir = "/tmp"
        else:
            self._work_dir = f"C:\\Windows\\Temp\\.run-{self.run_id[:8]}"
            try:
                await asyncio.to_thread(
                    self._remote_runner.run, f'mkdir "{self._work_dir}" 2>nul'
                )
            except Exception:
                self._work_dir = "C:\\Windows\\Temp"

    def _build_provider_kwargs(self, cfg: CloudConfig) -> dict[str, Any]:
        """Build kwargs for CloudProviderRegistry.create()."""
        from ofx.cloud.runtime import build_provider_kwargs

        return build_provider_kwargs(cfg)

    def _create_remote_runner(self, cfg: CloudConfig):
        """Create PostSSH or PostWinRM instance for the provisioned instance."""
        from ofx.cloud.runtime import create_remote_runner

        if not self._instance:
            raise RuntimeError("Cannot create remote runner without instance info")
        ip = self._instance.ip
        is_windows = cfg.connection_type == "winrm"
        is_log_commands = cfg.log_commands or False
        log_path = None
        if is_log_commands:
            if self.ctx.output_path:
                log_dir = Path(self.ctx.output_path) / "logs" / "cloud_commands"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"{self.model.jid}_{ip}.log"
            else:
                fd, tmp = tempfile.mkstemp(prefix=".tmp_rcmd_", suffix=".log")
                os.close(fd)
                log_path = tmp
            self._log_info(
                f"Command logging enabled. Logs will be saved to: {log_path}"
            )
        return create_remote_runner(
            cfg,
            ip,
            log_path=str(log_path) if log_path else None,
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

        await self._upload_fleet_input()
        await self._run_steps(None)

    async def _run_steps(
        self,
        matrix_combo: dict[str, Any] | None,
        suffix: str = "",
    ) -> None:
        """Execute all job steps on the remote VPS.

        Subclasses (e.g. ``CloudMatrixJobRunner``) call this repeatedly
        with different *matrix_combo* dicts to iterate over matrix
        combinations on the same host.
        """
        loop_ctx = self._child_context()
        if matrix_combo:
            if "matrix" not in loop_ctx.vars:
                loop_ctx.vars["matrix"] = {}
            loop_ctx.vars["matrix"].update(matrix_combo)

        for step in self.model.steps:
            step_ctx = loop_ctx.model_copy(deep=True)
            if step.secrets != "inherit":
                step_ctx.secrets = {}

            step_runner = CloudStepRunner(
                step,
                step_ctx,
                self,
                remote_runner=self._remote_runner,
                work_dir=self._work_dir,
            )
            runner_key = f"{step.step_index}{suffix}"
            self._runners[runner_key] = step_runner
            result = await step_runner.run()
            if step_runner.is_failed and not step.continue_on_error:
                raise RuntimeError(
                    job_step_failed(step.name or step.step_index, result.error)
                )

    # ------------------------------------------------------------------
    # Post-run: collect outputs, destroy
    # ------------------------------------------------------------------

    async def _post_run(self) -> None:
        if self.model.outputs:
            resolved_outputs = {}
            for key, value in self.model.outputs.items():
                resolved_value = await self._resolve_template(value)
                resolved_outputs[key] = resolved_value
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, resolved_outputs)

        job_exec = build_job_execution_result(self, self._runners)
        await self.reg_set(RunnerRegistryKeys.EXECUTION, job_exec.to_dict())

        await self._download_outputs()
        await self._destroy_instance()
        await self._cleanup_remote()

    async def _download_outputs(self) -> None:
        """Download output files from remote VPS."""
        if not self.ctx.output_path or not self._remote_runner:
            return

        is_windows = self._cloud_config.connection_type == "winrm"

        try:
            if is_windows:
                files_output = await asyncio.to_thread(
                    self._remote_runner.run,
                    f"powershell \"Get-ChildItem -Path '{self._work_dir}\\output' "
                    f'-File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name"',
                )
            else:
                files_output = await asyncio.to_thread(
                    self._remote_runner.run,
                    f"ls -1 {self._work_dir}/output 2>/dev/null || true",
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
                    await asyncio.to_thread(self._remote_runner.download, remote, local)
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
                f"Destroying instance '{self._instance.name}'[{self._instance.instance_id}] "
                f"(provider={self._instance.provider})"
            )
            await self._provider.destroy_instance(self._instance.instance_id)
        except Exception as e:
            self._log_warning(f"Instance destroy failed: {e}")

    async def _cleanup_remote(self) -> None:
        """Clean up remote working directory and runner resources."""
        if not self._remote_runner:
            return
        # Remove remote work dir and all contents
        if self._work_dir and self._work_dir not in ("/tmp", "C:\\Windows\\Temp"):
            try:
                is_windows = (
                    self._cloud_config and self._cloud_config.connection_type == "winrm"
                )
                if is_windows:
                    await asyncio.to_thread(
                        self._remote_runner.run,
                        f"powershell \"Remove-Item -Path '{self._work_dir}' -Recurse -Force -ErrorAction SilentlyContinue\"",
                        15,
                    )
                else:
                    await asyncio.to_thread(
                        self._remote_runner.run, f"rm -rf {self._work_dir}", 15
                    )
            except Exception:
                pass
        if hasattr(self._remote_runner, "cleanup"):
            try:
                await asyncio.to_thread(self._remote_runner.cleanup)
            except Exception:
                pass

    async def _handle_failure(self, *, prompt_destroy: bool = True) -> None:
        """Salvage outputs from the remote VPS, then ask user about destruction.

        Args:
            prompt_destroy: Whether to interactively prompt about VPS
                destruction.  Set to ``False`` when the caller (e.g.
                ``CloudMatrixJobRunner``) will handle the prompt for all
                surviving instances in a single batch.

        Order of operations:
        1. Download any outputs that were produced before the failure.
        2. If *prompt_destroy* and the provider is not static, prompt the
           user (TTY) or log a warning (non-TTY) with instance details.
        3. Clean up the SSH/WinRM transport.
        """
        # 1. Try to salvage outputs
        try:
            await self._download_outputs()
        except Exception as e:
            self._log_debug(f"Output salvage on failure failed: {e}")

        if not prompt_destroy:
            # Caller will handle destroy prompt — just clean transport.
            await self._cleanup_remote()
            return

        # 2. Decide whether to destroy
        is_static = (
            self._cloud_config and (self._cloud_config.provider or "static") == "static"
        )
        has_instance = self._provider and self._instance

        if has_instance and not is_static and self._instance:
            instance_desc = (
                f"{self._instance.name} [{self._instance.instance_id}] "
                f"@ {self._instance.ip} "
                f"(provider={self._instance.provider})"
            )

            should_destroy = await _prompt_destroy_instance(instance_desc)

            if should_destroy:
                await self._destroy_instance()
            else:
                self._log_warning(
                    f"Instance left running: {instance_desc}  — "
                    "destroy manually when done."
                )

        # 3. Clean up SSH/WinRM transport (does NOT destroy the VPS)
        await self._cleanup_remote()

    async def _upload_fleet_input(self) -> None:
        """Upload the local fleet chunk file to the remote host.

        When this CloudJobRunner is spawned by CloudMatrixJobRunner with
        fleet expansion, ``ctx.vars["fleet"]["fleet_input_file"]`` points to a
        local temp file.  We upload it and set explicit remote env vars.
        """
        fleet_vars = self.ctx.vars.get("fleet", {})
        local_path = fleet_vars.get("fleet_input_file", "")

        # Inject other fleet variables as remote env vars.
        # fleet_input is a Python list — export as newline-joined string so it
        # is usable inside shell scripts without parsing Python repr.
        for k, v in fleet_vars.items():
            if k == "fleet_input_file":
                continue
            remote_key = f"REMOTE_{k.upper()}"
            if isinstance(v, list):
                str_val = "\n".join(str(x) for x in v)
            else:
                str_val = str(v)
            self.ctx.envs[remote_key] = str_val
            self.ctx.vars[f"remote_{k}"] = v

        if not local_path:
            return

        local = Path(local_path)
        if not local.is_file():
            return

        if not self._remote_runner or not self._work_dir:
            return

        is_windows = (
            self._cloud_config and self._cloud_config.connection_type == "winrm"
        )
        if is_windows:
            remote_path = f"{self._work_dir}\\fleet_targets.txt"
        else:
            remote_path = f"{self._work_dir}/fleet_targets.txt"

        try:
            await asyncio.to_thread(self._remote_runner.upload, str(local), remote_path)
            # Use explicit "remote" prefix to avoid runtime env modification anti-pattern
            self.ctx.envs["REMOTE_FLEET_INPUT_FILE"] = remote_path
            self.ctx.vars["remote_fleet_input_file"] = remote_path
            self._log_info(f"Uploaded fleet input → {remote_path}")
        except Exception as e:
            raise RuntimeError(
                f"Failed to upload fleet input file '{local}' → '{remote_path}': {e}"
            ) from e

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        workflow_name = ""
        if self.parent and getattr(self.parent, "model", None):
            workflow_name = getattr(self.parent.model, "name", "") or ""
        msg = (
            f"workflow[{workflow_name}] "
            f"job[{self.model.jid}] [cloud] › {message_str}"
        )
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    @property
    def remote_work_dir(self) -> str | None:
        return self._work_dir
