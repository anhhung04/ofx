"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ofx.api.bundle.builder import build_bundle
from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.execution.error_helpers import job_step_failed
from ofx.runner.execution.execution_results import (
    StepExecutionResult,
    build_job_execution_result,
    build_run_if_context,
)
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

    async def run(self, *args, **kwargs):
        """Override to ensure VPS cleanup on any failure."""
        try:
            return await super().run(*args, **kwargs)
        except Exception:
            # Ensure remote resources are cleaned up on failure
            self._cleanup_remote()
            await self._destroy_instance()
            raise

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

        if not self._instance or not self._instance.ip:
            raise RuntimeError("Instance has no IP address")

        is_windows = cfg.connection_type == "winrm"
        await wait_for_connectivity(
            host=self._instance.ip,
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
            kwargs["host"] = cfg.host or self._cloud_config.host
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
        is_log_commands = cfg.log_commands or False
        log_path = None
        if is_log_commands:
            if self.ctx.output_path:
                log_dir = Path(self.ctx.output_path) / "logs"/ "cloud_commands"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"{self.model.jid}_{ip}.log"
            else:
                fd, tmp = tempfile.mkstemp(prefix="ofx_cloud_commands_", suffix=".log")
                os.close(fd)
                log_path = tmp
            self._log_info(f"Command logging enabled. Logs will be saved to: {log_path}")
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
                log_path=str(log_path) if log_path else None,
            )

        return RunnerRegistry.create(
            "ssh",
            host=ip,
            user=cfg.ssh_user or "root",
            port=cfg.ssh_port or 22,
            identity_file=cfg.ssh_key,
            password=cfg.ssh_password,
            opsec_mode=cfg.opsec_mode or False,
            log_commands=cfg.log_commands or False,
            max_retries=3,
            log_path=str(log_path) if log_path else None,
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
        self._cleanup_remote()

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
            self._log_warning(f"Instance destroy failed: {e}")

    def _cleanup_remote(self) -> None:
        """Clean up remote runner resources."""
        if self._remote_runner and hasattr(self._remote_runner, "cleanup"):
            try:
                self._remote_runner.cleanup()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
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

        raise RuntimeError(f"Step failed after {retry + 1} attempts:\n{last_error}")

    async def _post_run(self) -> None:
        result = await self.get_result()
        stdout = result.outputs.get("stdout", "")

        self._log_output("stdout", stdout)

        # Save full output to log file if configured
        if self.model.log_stdout and stdout and self.ctx.output_path:
            self._save_output(stdout)

        status_value = (
            RunnerStatus.COMPLETED.value
            if result.status == RunnerStatus.FINISHED
            else result.status.value
        )
        execution = StepExecutionResult(
            step_index=self.model.step_index,
            name=self.model.name,
            run_type=self._run_type.value if self._run_type else self.model.get_run_type().value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

    def _log_output(self, stream: str, content: str) -> None:
        """Log a stdout/stderr stream to the console."""
        if not content or not isinstance(content, str):
            return
        for line in content.splitlines():
            self._log_info(f"{stream} | {line}")

    # ------------------------------------------------------------------
    # Remote execution methods
    # ------------------------------------------------------------------

    async def _run_remote_command(self, command: str, timeout: int | None = None) -> str:
        """Run a shell command on the remote host."""
        env_prefix = self._build_env_prefix()
        work_dir = self._resolve_remote_work_dir()

        full_cmd = ""
        if env_prefix:
            full_cmd += env_prefix + " "
        full_cmd += f"cd {work_dir} && {command}"

        return await asyncio.to_thread(
            self._remote.run, full_cmd, timeout
        )

    async def _discover_python(self) -> str:
        """Find a working python3/python executable on the remote host."""
        if hasattr(self, "_cached_python"):
            return self._cached_python

        candidates = [
            "python3",
            "python",
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python",
            "/usr/local/bin/python",
        ]
        for candidate in candidates:
            try:
                output = await asyncio.to_thread(
                    self._remote.run,
                    f"command -v {candidate} 2>/dev/null && {candidate} --version 2>&1",
                    10,
                )
                if output.strip():
                    self._cached_python = candidate
                    self._log_info(f"Discovered Python: {candidate}")
                    return candidate
            except Exception:
                continue

        raise RuntimeError(
            "No python3 or python executable found on the remote host. "
            "Checked: " + ", ".join(candidates)
        )

    async def _run_remote_script(self, script: str, timeout: int | None = None) -> str:
        """Run an inline Python script on the remote host.

        The script is bundled with its required ``ofx.api`` modules via
        :func:`ofx.api.bundle.builder.build_bundle` so that OFX API imports
        are available on the remote host without installing the package.
        """
        import secrets as _secrets

        # Build bundle to inject ofx.api dependencies
        bundle = build_bundle(script)

        # Discover python on the remote host
        python_bin = await self._discover_python()

        remote_script = f"{self._work_dir}/.ofx_script_{_secrets.token_hex(4)}.py"

        # Upload bundled script content
        fd, local_tmp = tempfile.mkstemp(prefix="ofx_script_", suffix=".py")
        os.close(fd)
        try:
            Path(local_tmp).write_text(bundle.bootstrap)
            await asyncio.to_thread(self._remote.upload, local_tmp, remote_script)
        finally:
            Path(local_tmp).unlink(missing_ok=True)

        # Execute
        try:
            env_prefix = self._build_env_prefix()
            work_dir = self._resolve_remote_work_dir()
            full_cmd = f"cd {work_dir} && "
            if env_prefix:
                full_cmd += env_prefix + " "
            full_cmd += f"{python_bin} {remote_script}"
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
        """Upload and run a script file on the remote host using the bundle API.

        The script file is bundled with its required ``ofx.api`` modules via
        :func:`ofx.api.bundle.builder.build_bundle`. The resulting bootstrap is
        uploaded to the remote host and executed with the discovered python
        interpreter. The stdout of the remote execution is returned.
        """
        # Resolve the absolute path of the script file.
        local_path = Path(script_file).expanduser().with_suffix(".py")
        
        if not local_path.is_absolute():
            base_dir = getattr(self.ctx, "workflow_dir", Path.cwd())
            local_path = (base_dir / local_path).resolve()
        
        if not local_path.is_file():
            raise FileNotFoundError(f"Script file not found: {local_path}")

        script_content = local_path.read_text()
        # Build a bundle that includes any OFX API imports used by the script.
        bundle = build_bundle(script_content)

        # Discover python on the remote host.
        python_bin = await self._discover_python()

        # Write bootstrap to a temporary local file.
        fd, local_tmp = tempfile.mkstemp(prefix="ofx_bundle_", suffix=".py")
        os.close(fd)
        remote_path = "/tmp/__UNKNOWN__"
        try:
            Path(local_tmp).write_text(bundle.bootstrap)
            remote_path = f"{self._work_dir}/{Path(local_tmp).name}"
            # Upload the bootstrap to the remote host.
            await asyncio.to_thread(self._remote.upload, local_tmp, remote_path)

            # Execute the bootstrap via discovered python on the remote host.
            work_dir = self._resolve_remote_work_dir()
            env_prefix = self._build_env_prefix()
            exec_cmd = f"cd {work_dir} && "
            if env_prefix:
                exec_cmd += env_prefix + " "
            exec_cmd += f"{python_bin} {remote_path}"
            return await asyncio.to_thread(self._remote.run, exec_cmd, timeout)
        finally:
            # Clean up temporary local file.
            Path(local_tmp).unlink(missing_ok=True)
            # Clean up remote file.
            try:
                await asyncio.to_thread(self._remote.run, f"rm -f {remote_path}", 10)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_remote_work_dir(self) -> str:
        """Resolve the working directory for remote execution.

        Uses the remote work dir (e.g. /tmp/ofx-xxxx) by default.
        Only honours ``model.working_directory`` when it looks like a
        remote-appropriate path (absolute *and* different from any local
        default that leaked from workflow defaults).
        """
        model_wd = getattr(self.model, "working_directory", None)
        if model_wd and model_wd not in (".", ""):
            # Only use the model value if it's an absolute remote path
            # and not clearly a local path (heuristic: starts with /tmp,
            # /home on the remote, /opt, /var, /root, /srv etc. are fine,
            # but the local cwd like /home/<user>/projects/... is wrong).
            # Safest: only use it if it starts with the remote work dir prefix
            # or if the user explicitly set it (not the workflow default).
            parent_default = None
            parent = self.parent
            if parent and hasattr(parent, "model"):
                defaults = getattr(parent.model, "defaults", None)
                if defaults and hasattr(defaults, "run"):
                    parent_default = getattr(defaults.run, "working_directory", None)
            if model_wd != parent_default and model_wd != ".":
                # User explicitly set a working_directory on the step — trust it
                return model_wd
        return self._work_dir

    def _build_env_prefix(self) -> str:
        """Build environment variable export prefix for remote command.

        Only exports env vars explicitly configured in the workflow/job/step
        model ``env:`` fields — never the local OS environment.
        """
        env_vars: dict[str, str] = {}

        # Workflow-level env (propagated through parent job model)
        parent = self.parent
        if parent and hasattr(parent, "model") and hasattr(parent.model, "env"):
            parent_env = parent.model.env
            if parent_env:
                env_vars.update(parent_env)

        # Step-level env
        if hasattr(self.model, "env") and self.model.env:
            env_vars.update(self.model.env)

        if not env_vars:
            return ""

        exports = " ".join(
            f'{k}="{v}"' for k, v in env_vars.items()
        )
        return f"export {exports} &&" if exports else ""

    def _save_output(self, output: str) -> None:
        """Save step output to local log file (mirrors StepRunner format)."""
        if not self.ctx.output_path:
            return
        log_path = Path(self.ctx.output_path) / "logs"
        log_path.mkdir(parents=True, exist_ok=True)

        job_id = self.parent.model.jid if self.parent else "unknown"
        step_name = (self.model.name or f"step_{self.model.step_index}").replace(" ", "-")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = log_path / f"stdout_{job_id}_{step_name}__{timestamp}.log"

        log_lines = []
        if self.model.run:
            log_lines.append(f">> command: {self.model.run}")
        elif self.model.script_file:
            log_lines.append(f">> script_file: {self.model.script_file}")
        elif self.model.script:
            log_lines.append(">> script (inline)")
        else:
            log_lines.append(">> unknown step type")
        log_lines.append(">>===<<")
        log_lines.append(output)
        out_file.write_text("\n".join(log_lines))
        self._log_info(f"Saved output to {out_file}")

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"step[{self.model.step_index}] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
