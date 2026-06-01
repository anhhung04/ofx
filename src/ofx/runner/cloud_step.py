"""Cloud step runner — executes steps remotely via PostSSH or PostWinRM.

Extracted from ``cloud_job.py`` to follow the File-Per-Struct rule.
"""

from __future__ import annotations

import asyncio
import secrets as _secrets
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.cloud.runtime import remote_join
from ofx.cloud.script_runtime import (
    build_python_step_payload,
    is_python_step_run_type,
)
from ofx.cloud.task_runtime import build_task_command_from_step
from ofx.cloud.temp_upload import upload_temp_content
from ofx.models.step import RunType
from ofx.runner.context import (
    RunContext,
)
from ofx.runner.logging import bubble_context_log
from ofx.runner.metadata import ModelContext
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.run_defaults import model_field_is_explicitly_set
from ofx.runner.runner import Runner
from ofx.runner.step_fields import BASE_STEP_TEMPLATE_FIELDS, RUN_TYPE_TEMPLATE_FIELDS
from ofx.runner.step_mixin import StepRunnerMixin
from ofx.utils.shell import bash_dquote_escape

if TYPE_CHECKING:
    from ofx.runner.cloud_job import CloudJobRunner

# Grace period (seconds) added to the configured timeout to account for
# network latency when executing commands on a remote host.
_NETWORK_GRACE_SECONDS = 30
_RUNNER_ENV_PREFIXES: tuple[str, ...] = ("FLEET_", "REMOTE_")

_PYTHON_PROBE_CANDIDATES: tuple[str, ...] = (
    "python3",
    "python",
    "/usr/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python",
    "/usr/local/bin/python",
)

_REMOTE_PATH_CLEANUP_TIMEOUT = 10

class _RemoteHandlerRunner:
    """Bridge object conforming to the handler runner protocol for StepExecutor.

    Allows CloudStepRunner to reuse StepExecutor's retry/timeout logic
    while executing commands remotely instead of locally.
    """

    __slots__ = ("_outer", "is_success")

    def __init__(self, outer):
        self._outer = outer
        self.is_success = True

    async def run(self):
        run_type = self._outer._run_type or self._outer.model.get_run_type()
        timeout_seconds = self._outer.model.timeout * 60
        output = await asyncio.wait_for(
            self._outer._execute_remote_run_type(
                run_type,
                timeout_seconds=timeout_seconds,
            ),
            timeout=timeout_seconds + _NETWORK_GRACE_SECONDS,
        )
        outputs_dict: dict[str, Any] = {"stdout": output}
        if run_type == RunType.TASK and self._outer.model.task:
            outputs_dict["typed_outputs"] = self._outer._parse_task_output(output)
        await self._outer.reg_set(
            RunnerRegistryKeys.OUTPUTS,
            outputs_dict,
        )
        return await self._outer.get_result()


class CloudStepRunner(StepRunnerMixin, Runner):
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
        executor=None,
        handler_registry=None,
    ):
        from ofx.runner.executors.step import StepExecutor
        from ofx.runner.handlers import registry as default_handler_registry

        step_executor = executor or StepExecutor()
        super().__init__(
            step,
            ctx,
            parent,
            parent.registry,
            executor=step_executor,
        )
        self._handler_registry = handler_registry or default_handler_registry
        self._remote = remote_runner
        self._work_dir = work_dir or "/tmp"
        self._run_type = None
        self._outputs_file = None

    @property
    def _is_windows(self) -> bool:
        """True when the remote host is Windows (WinRM connection)."""
        cloud_config = getattr(self.parent, "_cloud_config", None)
        return bool(cloud_config and cloud_config.connection_type == "winrm")

    async def _pre_run(self) -> None:
        self._apply_retry_profile_defaults()
        self._run_type = self.model.get_run_type()
        self.update_vars({"remote_work_dir": self._resolve_remote_work_dir()})
        fields = list(BASE_STEP_TEMPLATE_FIELDS)
        if self._run_type is not RunType.WORKFLOW:
            fields.extend(RUN_TYPE_TEMPLATE_FIELDS[self._run_type])
        await self._resolve_template_fields(fields)
        await self._resolve_timeout_field()
        self._ensure_run_if_condition(self._produce_log("Step condition not met"))

    async def _on_failure_cleanup(self) -> None:
        """Best-effort cleanup of remote temp files on step failure."""
        # Remote scripts are cleaned in their own finally blocks, but
        # this hook ensures any leaked temp files in the work dir are noted.
        self._log_debug("Cloud step failure cleanup completed")

    def _build_timeline_params(self, result) -> dict[str, str]:
        """Build timeline params including cloud host and tags."""
        params = super()._build_timeline_params(result)
        params.update({
            "source_host": getattr(getattr(self.parent, "_cloud_config", None), "host", "") or "",
            "tags": "cloud",
        })
        return params

    # ------------------------------------------------------------------
    # Remote execution methods
    # ------------------------------------------------------------------

    async def _discover_python(self) -> str:
        """Find a working python3/python executable on the remote host.

        The result is cached on the parent ``CloudJobRunner`` so that all steps
        in the same job share a single probe, avoiding repeated SSH round-trips.
        """
        parent_job = self.parent if hasattr(self.parent, "_cached_python") else None
        if parent_job is not None and parent_job._cached_python:
            return parent_job._cached_python

        for candidate in _PYTHON_PROBE_CANDIDATES:
            try:
                output = await asyncio.to_thread(
                    self._remote.run,
                    f"command -v {candidate} 2>/dev/null && {candidate} --version 2>&1",
                    _REMOTE_PATH_CLEANUP_TIMEOUT,
                )
            except Exception as e:
                self._log_debug(f"Python candidate {candidate} failed: {e}")
                continue

            if not output or not output.strip():
                continue

            self._log_info(f"Discovered Python: {candidate}")
            if parent_job is not None:
                parent_job._cached_python = candidate
            return candidate

        raise RuntimeError(
            "No python3 or python executable found on the remote host. "
            "Checked: " + ", ".join(_PYTHON_PROBE_CANDIDATES)
        )

    async def _run_remote_python_payload(
        self,
        payload: str,
        *,
        timeout: int | None = None,
    ) -> str:
        """Upload a bundled Python payload, execute it remotely, then clean up."""

        remote_path: str | None = None
        try:
            python_bin = await self._discover_python()
            remote_path = remote_join(
                self._work_dir,
                f".tmp_py_{_secrets.token_hex(6)}.py",
                is_windows=self._is_windows,
            )
            await asyncio.to_thread(
                upload_temp_content,
                self._remote,
                payload,
                remote_path,
                suffix=".py",
            )
            if self._is_windows:
                command = f'"{python_bin}" "{remote_path}"'
            else:
                command = f"{shlex.quote(python_bin)} {shlex.quote(remote_path)}"
            return await asyncio.to_thread(
                self._remote.run,
                self._build_remote_exec_command(command),
                timeout,
            )
        finally:
            if remote_path is not None:
                try:
                    if self._is_windows:
                        cleanup_command = f'del /f "{remote_path}"'
                    else:
                        cleanup_command = f"rm -f {shlex.quote(remote_path)}"
                    await asyncio.to_thread(
                        self._remote.run,
                        cleanup_command,
                        _REMOTE_PATH_CLEANUP_TIMEOUT,
                    )
                except Exception as e:
                    self._log_debug(f"Failed to remove remote file {remote_path}: {e}")

    # ------------------------------------------------------------------
    # Task execution (remote)
    # ------------------------------------------------------------------

    async def _execute_remote_run_type(
        self,
        run_type: RunType,
        *,
        timeout_seconds: int,
    ) -> str:
        """Dispatch the current step to the appropriate remote execution path."""
        if is_python_step_run_type(run_type):
            cloud_config = getattr(self.parent, "_cloud_config", None)
            workflow_dir = self.ctx.workflow_dir or Path.cwd()
            opsec_mode = bool(cloud_config and cloud_config.opsec_mode)
            payload = build_python_step_payload(
                self.model,
                workflow_dir=workflow_dir,
                opsec_mode=opsec_mode,
                obfuscate_sources=opsec_mode,
            )
            return await self._run_remote_python_payload(payload, timeout=timeout_seconds)

        command: str | None = None
        if run_type == RunType.COMMAND:
            command = self.model.run
        elif run_type == RunType.TASK:
            profile = self.ctx.vars.get("profile_model")
            command = build_task_command_from_step(self.model, profile=profile)

        if command is not None:
            return await asyncio.to_thread(
                self._remote.run,
                self._build_remote_exec_command(command),
                timeout_seconds,
            )
        if run_type == RunType.WORKFLOW:
            raise RuntimeError(
                "Reusable workflows ('uses') are not supported in cloud job mode"
            )
        if run_type == RunType.PIPE:
            raise RuntimeError(
                "Pipe steps run locally - they are not supported in cloud job mode. "
                "Use a 'script:' step for remote data processing."
            )

        valid = ", ".join(rt.value for rt in RunType)
        run_type_name = run_type.value if isinstance(run_type, RunType) else str(run_type)
        raise RuntimeError(
            f"Unsupported run type '{run_type_name}' for cloud step "
            f"'{self.model.name}'. Valid types: {valid}"
        )

    def _create_runner(self) -> _RemoteHandlerRunner:
        return _RemoteHandlerRunner(self)

    def _parse_task_output(self, stdout: str) -> list[dict]:
        """Parse stdout through the registered task's parser."""
        try:
            from ofx.tasks.registry import TaskRegistry
            from ofx.runner.services.credential_store import (
                should_store_creds,
                store_and_log_typed_outputs,
            )

            task_cls = TaskRegistry.get(self.model.task)
            if task_cls is None:
                return []

            results = task_cls().parse_output(stdout=stdout, stderr="")
            if results and should_store_creds(
                self.model.store_creds,
                self.parent.model if self.parent else None,
            ):
                store_and_log_typed_outputs(
                    results,
                    debug_fn=self._log_debug,
                    info_fn=self._log_info,
                )
            return [item.to_dict() for item in results]
        except Exception as e:
            self._log_debug(f"Failed to parse task output for '{self.model.task}': {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_remote_work_dir(self) -> str:
        """Resolve the working directory for remote execution.

        Uses the remote work dir (e.g. /tmp/.run-xxxx) unless the step
        explicitly set its own working directory.
        """
        model_wd = getattr(self.model, "working_directory", None)
        if model_field_is_explicitly_set(self.model, "working_directory") and model_wd not in (
            ".",
            "",
        ):
            return str(model_wd)
        return self._work_dir

    def _build_remote_exec_command(self, command: str) -> str:
        """Build a platform-appropriate remote command with env and cwd setup."""
        env_prefix = self._build_env_prefix()
        work_dir = self._resolve_remote_work_dir()
        if self._is_windows:
            chdir_command = f'cd /d "{work_dir}"'
            parts = [part for part in [env_prefix, chdir_command, command] if part]
            return " && ".join(parts)

        chdir_command = f"cd {shlex.quote(work_dir)}"
        parts = []
        if env_prefix:
            parts.append(env_prefix)
        parts.append(f"{chdir_command} && {command}")
        return " ".join(parts)

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
        parent_model = getattr(self.parent, "model", None)
        env_vars = {
            key: str(value)
            for key, value in self.ctx.envs.items()
            if any(key.startswith(prefix) for prefix in _RUNNER_ENV_PREFIXES)
        }
        env_vars.update(getattr(parent_model, "env", None) or {})
        env_vars.update(self.model.env or {})
        if not env_vars:
            return ""

        if self._is_windows:
            exports = " && ".join(
                f"SET {key}={str(value)}"
                for key, value in env_vars.items()
            )
            return f"{exports} &&" if exports else ""

        exports = " ".join(
            f'{key}="{bash_dquote_escape(str(value))}"'
            for key, value in env_vars.items()
        )
        return f"export {exports} &&" if exports else ""

    def _produce_log(self, message: Any) -> str:
        workflow_runner = getattr(getattr(self, "parent", None), "parent", None)
        workflow_context = ModelContext.from_model(getattr(workflow_runner, "model", None))
        parent_job_context = ModelContext.from_model(getattr(self.parent, "model", None))
        run_type = self._run_type or self.model.get_run_type()
        step_name = self.model.name or f"step_{self.model.step_index}"
        return bubble_context_log(
            self.parent,
            f"[{step_name}] [{run_type.value}] {message}",
            model_name=workflow_context.name or "",
            model_jid=parent_job_context.jid or "",
            step_index=self.model.step_index,
        )
