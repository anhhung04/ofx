"""Cloud step runner — executes steps remotely via PostSSH or PostWinRM.

Extracted from ``cloud_job.py`` to follow the File-Per-Struct rule.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.api.bundle.builder import build_bundle
from ofx.runner.core import (
    BaseRunner,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.execution.execution_results import StepExecutionResult
from ofx.runner.logging import get_logger

if TYPE_CHECKING:
    from ofx.runner.execution.cloud_job import CloudJobRunner

logger = get_logger()


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
                elif run_type == RunType.TASK:
                    output = await self._run_remote_task(timeout=timeout_secs)
                else:
                    raise RuntimeError(f"Unknown run type: {run_type}")

                # Store output
                if output:
                    outputs_dict: dict[str, Any] = {"stdout": output}
                    # Parse typed outputs for task steps
                    if run_type == RunType.TASK and self.model.task:
                        outputs_dict["typed_outputs"] = self._parse_task_output(output)
                    await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs_dict)

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
            run_type=self._run_type.value
            if self._run_type
            else self.model.get_run_type().value,
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
        self._log_info(f"\n==={stream}===\n{content}===========")

    # ------------------------------------------------------------------
    # Remote execution methods
    # ------------------------------------------------------------------

    async def _run_remote_command(
        self, command: str, timeout: int | None = None
    ) -> str:
        """Run a shell command on the remote host."""
        env_prefix = self._build_env_prefix()
        work_dir = self._resolve_remote_work_dir()

        full_cmd = ""
        if env_prefix:
            full_cmd += env_prefix + " "
        full_cmd += f"cd {work_dir} && {command}"

        return await asyncio.to_thread(self._remote.run, full_cmd, timeout)

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

        remote_script = f"{self._work_dir}/.s_{_secrets.token_hex(6)}.py"

        # Upload bundled script content
        fd, local_tmp = tempfile.mkstemp(prefix=".tmp_s_", suffix=".py")
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
                await asyncio.to_thread(self._remote.run, f"rm -f {remote_script}", 10)
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
        fd, local_tmp = tempfile.mkstemp(prefix=".tmp_b_", suffix=".py")
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
    # Task execution (remote)
    # ------------------------------------------------------------------

    async def _run_remote_task(self, timeout: int | None = None) -> str:
        """Build a task command locally and run it on the remote host.

        The task's ``build_command`` generates the CLI invocation.  Since
        the structured output file lives on the remote host we cannot
        parse it locally, so we rely on stdout/stderr parsing only.
        """
        from ofx.tasks.registry import TaskRegistry

        task_cls = TaskRegistry.get(self.model.task)
        if task_cls is None:
            raise RuntimeError(f"Task '{self.model.task}' is not registered")

        task = task_cls()

        # Extract target from run_with; remaining keys are task options
        task_opts = dict(self.model.run_with)
        target = str(task_opts.pop("target", task_opts.pop("targets", "")))

        # Build command — disable output_flag so no temp file is created
        saved_output_flag = task.output_flag
        try:
            task.output_flag = None
            cmd_str, _ = task.build_command(target, **task_opts)
        finally:
            task.output_flag = saved_output_flag

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
            return [r.to_dict() for r in results]
        except Exception:
            return []

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
        1. Runner-injected context envs (e.g. REMOTE_FLEET_INPUT_FILE from fleet expansion)
        2. Workflow/job-level ``env:`` fields (propagated through parent model)
        3. Step-level ``env:`` field

        Later sources override earlier ones. Local OS environment is never leaked.
        """
        env_vars: dict[str, str] = {}

        # Runner-injected env vars (fleet vars, etc.) — only export known prefixes
        _RUNNER_ENV_PREFIXES = ("FLEET_",)
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

        exports = " ".join(f'{k}="{v}"' for k, v in env_vars.items())
        return f"export {exports} &&" if exports else ""

    def _save_output(self, output: str) -> None:
        """Save step output to local log file (mirrors StepRunner format)."""
        if not self.ctx.output_path:
            return
        log_path = Path(self.ctx.output_path) / "logs"
        log_path.mkdir(parents=True, exist_ok=True)

        job_id = self.parent.model.jid if self.parent else "unknown"
        step_name = (self.model.name or f"step_{self.model.step_index}").replace(
            " ", "-"
        )
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
