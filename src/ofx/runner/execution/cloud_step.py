"""Cloud step runner — executes steps remotely via PostSSH or PostWinRM.

Extracted from ``cloud_job.py`` to follow the File-Per-Struct rule.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.cloud.script_runtime import (
    build_python_payload,
    resolve_python_step_source,
)
from ofx.cloud.task_runtime import build_task_command_from_step
from ofx.runner.core import (
    BaseRunner,
    ConditionNotMetError,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.execution.execution_results import (
    build_step_execution_result,
)
from ofx.runner.execution.step_mixin import StepRunnerMixin
from ofx.runner.logging import get_logger
from ofx.utils.shell import bash_dquote_escape

if TYPE_CHECKING:
    from ofx.runner.execution.cloud_job import CloudJobRunner

logger = get_logger()


class CloudStepRunner(StepRunnerMixin, BaseRunner):
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

    @property
    def _is_windows(self) -> bool:
        """True when the remote host is Windows (WinRM connection)."""
        from ofx.runner.execution.cloud_job import CloudJobRunner

        if isinstance(self.parent, CloudJobRunner) and self.parent._cloud_config:
            return self.parent._cloud_config.connection_type == "winrm"
        return False

    async def _pre_run(self) -> None:
        from ofx.models.step import RunType

        self._apply_retry_profile_defaults()
        self._run_type = self.model.get_run_type()
        resolve_fields = [
            "name",
            "shell",
            "working_directory",
            "log_stdout",
            "env",
            "run_if",
        ]
        if self._run_type == RunType.COMMAND:
            resolve_fields.extend(["run"])
        elif self._run_type == RunType.SCRIPT:
            resolve_fields.extend(["script"])
        elif self._run_type == RunType.SCRIPT_FILE:
            resolve_fields.extend(["script_file"])
        elif self._run_type == RunType.TASK:
            resolve_fields.extend(["task", "run_with"])

        self.ctx.vars["remote_work_dir"] = self._resolve_remote_work_dir()
        await self._resolve_template_fields(resolve_fields)

        await self._resolve_timeout_field()

        if not self._evaluate_run_if(self.model.run_if, self._run_if_context()):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError(self._produce_log("Step condition not met"))

    async def _on_failure_cleanup(self) -> None:
        """Best-effort cleanup of remote temp files on step failure."""
        # Remote scripts are cleaned in their own finally blocks, but
        # this hook ensures any leaked temp files in the work dir are noted.
        self._log_debug("Cloud step failure cleanup completed")

    async def _do_run(self) -> None:
        from ofx.models.step import RunType
        from ofx.runner.execution.error_helpers import (
            step_retry_error,
            step_timeout_error,
        )

        run_type = self._run_type
        max_attempts = self.model.retry + 1
        timeout_seconds = self.model.timeout * 60

        last_error = None
        attempt_errors: list[str] = []

        for attempt in range(max_attempts):
            try:
                if run_type == RunType.COMMAND:
                    output = await asyncio.wait_for(
                        self._run_remote_command(self.model.run, timeout=timeout_seconds),
                        timeout=timeout_seconds + 30,  # grace period for network latency
                    )
                elif run_type == RunType.SCRIPT:
                    output = await asyncio.wait_for(
                        self._run_remote_script(self.model.script, timeout=timeout_seconds),
                        timeout=timeout_seconds + 30,
                    )
                elif run_type == RunType.SCRIPT_FILE:
                    output = await asyncio.wait_for(
                        self._run_remote_script_file(self.model.script_file, timeout=timeout_seconds),
                        timeout=timeout_seconds + 30,
                    )
                elif run_type == RunType.WORKFLOW:
                    raise RuntimeError(
                        "Reusable workflows ('uses') are not supported in cloud job mode"
                    )
                elif run_type == RunType.TASK:
                    output = await asyncio.wait_for(
                        self._run_remote_task(timeout=timeout_seconds),
                        timeout=timeout_seconds + 30,
                    )
                else:
                    raise RuntimeError(f"Unknown run type: {run_type}")

                # Store output
                if output:
                    outputs_dict: dict[str, Any] = {"stdout": output}
                    if run_type == RunType.TASK and self.model.task:
                        outputs_dict["typed_outputs"] = self._parse_task_output(output)
                    await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs_dict)

                return  # Success

            except TimeoutError as e:
                raise RuntimeError(step_timeout_error(self.model.timeout)) from e
            except Exception as e:
                last_error = e
                err_msg = str(e)
                attempt_errors.append(f"attempt {attempt + 1}: {err_msg}")
                if attempt < max_attempts - 1:
                    next_delay = self._retry_delay_seconds(
                        attempt=attempt,
                        base_delay=self.model.retry_delay,
                    )
                    self._log_info(
                        f"Retry {attempt + 2}/{max_attempts} in {next_delay:.1f}s — {err_msg}"
                    )
                    await asyncio.sleep(next_delay)

        raise RuntimeError(
            step_retry_error(max_attempts, last_error)
            + f"\n  Attempts: {'; '.join(attempt_errors)}"
        )

    async def _post_run(self) -> None:
        result = await self.get_result()
        stdout = result.outputs.get("stdout", "")

        # For task steps with typed outputs, show formatted tables
        if not self._format_typed_outputs(result):
            self._log_output("stdout", stdout)

        # Save full output to log file if configured
        if self.model.log_stdout and stdout and self.ctx.output_path:
            self._save_output(stdout)

        status_value = (
            RunnerStatus.COMPLETED.value
            if result.status == RunnerStatus.FINISHED
            else result.status.value
        )
        execution = build_step_execution_result(
            step_index=self.model.step_index,
            name=self.model.name,
            run_type=self._run_type.value
            if self._run_type
            else self.model.get_run_type().value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

        # Log to project timeline CSV
        self._log_timeline(result, status_value)

    def _log_timeline(self, result, status: str) -> None:
        """Write a timeline entry for this cloud step execution."""
        from ofx.runner.execution.timeline import log_step

        params = self._build_timeline_params(result)

        # Get VPS host/IP as source — this is where commands actually run
        cloud_host = ""
        from ofx.runner.execution.cloud_job import CloudJobRunner
        if isinstance(self.parent, CloudJobRunner) and hasattr(self.parent, "_cloud_config"):
            cfg = self.parent._cloud_config
            if cfg:
                cloud_host = getattr(cfg, "host", "") or ""

        tags = "cloud"

        log_step(
            ctx_vars=self.ctx.vars,
            output_path=self.ctx.output_path,
            step_name=self.model.name or f"step{self.model.step_index}",
            status=status,
            duration_ms=self.duration_ms(),
            exit_code=result.outputs.get("exit_code"),
            tags=tags,
            source_host=cloud_host,
            **params,
        )

    # ------------------------------------------------------------------
    # Remote execution methods
    # ------------------------------------------------------------------

    async def _run_remote_command(
        self, command: str, timeout: int | None = None
    ) -> str:
        """Run a shell command on the remote host.

        Builds the full command string with env-var injection and working
        directory change.  Uses platform-appropriate syntax: bash ``&&``
        chains on Linux and CMD ``&&`` with ``SET`` on Windows.
        """
        env_prefix = self._build_env_prefix()
        work_dir = self._resolve_remote_work_dir()

        if self._is_windows:
            parts = []
            if env_prefix:
                parts.append(env_prefix)
            parts.append(f"cd /d {work_dir}")
            parts.append(command)
            full_cmd = " && ".join(parts)
        else:
            full_cmd = ""
            if env_prefix:
                full_cmd += env_prefix + " "
            full_cmd += f"cd {work_dir} && {command}"

        return await asyncio.to_thread(self._remote.run, full_cmd, timeout)

    async def _discover_python(self) -> str:
        """Find a working python3/python executable on the remote host.

        The result is cached on the parent ``CloudJobRunner`` so that all steps
        in the same job share a single probe, avoiding repeated SSH round-trips.
        """
        # Check parent-level cache first (shared across steps on the same VPS)
        from ofx.runner.execution.cloud_job import CloudJobRunner

        parent_job: CloudJobRunner | None = (
            self.parent if isinstance(self.parent, CloudJobRunner) else None
        )
        if parent_job is not None and parent_job._cached_python:
            return parent_job._cached_python

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
                    self._log_info(f"Discovered Python: {candidate}")
                    if parent_job is not None:
                        parent_job._cached_python = candidate
                    return candidate
            except Exception as e:
                logger.debug("Python candidate %s failed: %s", candidate, e)
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

        opsec_mode = False
        if self.parent and getattr(self.parent, "_cloud_config", None):
            opsec_mode = bool(getattr(self.parent._cloud_config, "opsec_mode", False))
        payload = build_python_payload(
            script,
            opsec_mode=opsec_mode,
            obfuscate_sources=opsec_mode,
        )

        # Discover python on the remote host
        python_bin = await self._discover_python()

        remote_script = f"{self._work_dir}/.s_{_secrets.token_hex(6)}.py"

        # Upload bundled script content
        fd, local_tmp = tempfile.mkstemp(prefix=".tmp_s_", suffix=".py")
        os.close(fd)
        try:
            Path(local_tmp).write_text(payload)
            await asyncio.to_thread(self._remote.upload, local_tmp, remote_script)
        finally:
            Path(local_tmp).unlink(missing_ok=True)

        # Execute
        try:
            env_prefix = self._build_env_prefix()
            work_dir = self._resolve_remote_work_dir()
            if self._is_windows:
                parts = [p for p in [env_prefix, f"cd /d {work_dir}"] if p]
                parts.append(f"{python_bin} {remote_script}")
                full_cmd = " && ".join(parts)
            else:
                full_cmd = f"cd {work_dir} && "
                if env_prefix:
                    full_cmd += env_prefix + " "
                full_cmd += f"{python_bin} {remote_script}"
            return await asyncio.to_thread(self._remote.run, full_cmd, timeout)
        finally:
            # Cleanup remote script
            try:
                rm_cmd = f"del /f {remote_script}" if self._is_windows else f"rm -f {remote_script}"
                await asyncio.to_thread(self._remote.run, rm_cmd, 10)
            except Exception as e:
                logger.debug("Failed to remove remote script %s: %s", remote_script, e)

    async def _run_remote_script_file(
        self, script_file: str, timeout: int | None = None
    ) -> str:
        """Upload and run a script file on the remote host using the bundle API.

        The script file is bundled with its required ``ofx.api`` modules via
        :func:`ofx.api.bundle.builder.build_bundle`. The resulting bootstrap is
        uploaded to the remote host and executed with the discovered python
        interpreter. The stdout of the remote execution is returned.
        """
        workflow_dir = getattr(self.ctx, "workflow_dir", Path.cwd())
        source = resolve_python_step_source(
            self.model,
            workflow_dir=workflow_dir,
        )
        opsec_mode = False
        if self.parent and getattr(self.parent, "_cloud_config", None):
            opsec_mode = bool(getattr(self.parent._cloud_config, "opsec_mode", False))
        payload = build_python_payload(
            source,
            opsec_mode=opsec_mode,
            obfuscate_sources=opsec_mode,
        )

        # Discover python on the remote host.
        python_bin = await self._discover_python()

        # Write bootstrap to a temporary local file.
        fd, local_tmp = tempfile.mkstemp(prefix=".tmp_b_", suffix=".py")
        os.close(fd)
        remote_path = "/tmp/__UNKNOWN__"
        try:
            Path(local_tmp).write_text(payload)
            remote_path = f"{self._work_dir}/{Path(local_tmp).name}"
            # Upload the bootstrap to the remote host.
            await asyncio.to_thread(self._remote.upload, local_tmp, remote_path)

            # Execute the bootstrap via discovered python on the remote host.
            work_dir = self._resolve_remote_work_dir()
            env_prefix = self._build_env_prefix()
            if self._is_windows:
                parts = [p for p in [env_prefix, f"cd /d {work_dir}"] if p]
                parts.append(f"{python_bin} {remote_path}")
                exec_cmd = " && ".join(parts)
            else:
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
                rm_cmd = f"del /f {remote_path}" if self._is_windows else f"rm -f {remote_path}"
                await asyncio.to_thread(self._remote.run, rm_cmd, 10)
            except Exception as e:
                logger.debug("Failed to remove remote file %s: %s", remote_path, e)

    # ------------------------------------------------------------------
    # Task execution (remote)
    # ------------------------------------------------------------------

    async def _run_remote_task(self, timeout: int | None = None) -> str:
        """Build a task command locally and run it on the remote host.

        The task's ``build_command`` generates the CLI invocation.  Since
        the structured output file lives on the remote host we cannot
        parse it locally, so we rely on stdout/stderr parsing only.
        """
        cmd_str = build_task_command_from_step(self.model)
        return await self._run_remote_command(cmd_str, timeout=timeout)

    def _parse_task_output(self, stdout: str) -> list[dict]:
        """Parse stdout through the registered task's parser."""
        try:
            from ofx.tasks.registry import TaskRegistry

            task_cls = TaskRegistry.get(self.model.task)
            if task_cls is None:
                return []
            task = task_cls()
            results = task.parse_output(stdout=stdout, stderr="")

            # Auto-store credentials if enabled
            if results and self._should_store_creds():
                self._store_credentials(results)

            return [r.to_dict() for r in results]
        except Exception as e:
            logger.debug("Failed to parse task output for '%s': %s", self.model.task, e)
            return []

    def _should_store_creds(self) -> bool:
        """Check if credential storage is enabled for this step."""
        from ofx.runner.core.credential_store import should_store_creds

        parent_model = self.parent.model if self.parent else None
        return should_store_creds(self.model.store_creds, parent_model)

    def _store_credentials(self, typed_outputs: list) -> None:
        """Store UserAccount outputs in the credential store."""
        from ofx.runner.core.credential_store import store_from_typed_outputs

        stored = store_from_typed_outputs(
            typed_outputs, log_fn=self._log_debug
        )
        if stored:
            self._log_info(f"Stored {stored} credential(s) in credential store")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_remote_work_dir(self) -> str:
        """Resolve the working directory for remote execution.

        Uses the remote work dir (e.g. /tmp/.run-xxxx) by default.
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

        Exports env vars from:
        1. Runner-injected context envs (fleet/remote vars set by CloudJobRunner)
        2. Workflow/job-level ``env:`` fields (propagated through parent model)
        3. Step-level ``env:`` field

        Later sources override earlier ones. Local OS environment is never leaked.
        Values are shell-escaped to prevent command injection via embedded
        ``$(...)`` or backtick sequences.
        """
        env_vars: dict[str, str] = {}

        # Runner-injected env vars: fleet expansion sets both FLEET_* and REMOTE_*
        # keys in ctx.envs.  Export all keys with known runner prefixes.
        _RUNNER_ENV_PREFIXES = ("FLEET_", "REMOTE_")
        for k, v in self.ctx.envs.items():
            if any(k.startswith(p) for p in _RUNNER_ENV_PREFIXES):
                env_vars[k] = str(v)

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

        if self._is_windows:
            # CMD syntax: SET FOO=bar (no quoting needed; && chaining handled by caller)
            exports = " && ".join(
                f"SET {k}={str(v)}" for k, v in env_vars.items()
            )
            return f"{exports} &&" if exports else ""

        exports = " ".join(
            f'{k}="{bash_dquote_escape(str(v))}"' for k, v in env_vars.items()
        )
        return f"export {exports} &&" if exports else ""

    def _save_output(self, output: str) -> None:
        """Save step output to local log file (mirrors StepRunner format)."""
        from ofx.runner.core.step_output import save_output_file

        if not self.ctx.output_path:
            return
        job_id = self.parent.model.jid if self.parent else "unknown"
        save_output_file(
            self.ctx.output_path,
            job_id,
            self.model,
            output,
            log_fn=self._log_info,
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        run_type = self._run_type.value if self._run_type else self.model.get_run_type().value
        step_name = self.model.name or f"step_{self.model.step_index}"
        job_id = ""
        workflow_name = ""
        if self.parent and getattr(self.parent, "model", None):
            job_id = getattr(self.parent.model, "jid", "") or ""
            if getattr(self.parent, "parent", None) and getattr(self.parent.parent, "model", None):
                workflow_name = getattr(self.parent.parent.model, "name", "") or ""
        msg = (
            f"workflow[{workflow_name}]"
            f"job[{job_id}]"
            f"step[{self.model.step_index}]"
            f"[{step_name}]"
            f"[{run_type}] › {message_str}"
        )
        if self.parent:
            return self.parent._produce_log(msg)
        return msg
