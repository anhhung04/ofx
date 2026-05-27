"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys, RunnerStatus
from ofx.runner.executors.cloud import CloudExecutor
from ofx.runner.executors.job import JobExecutor, MatrixExecutor
from ofx.runner.execution.job_mixin import JobRunnerMixin
from ofx.runner.logging import LogContext

if TYPE_CHECKING:
    from ofx.cloud.base import CloudProvider
    from ofx.cloud.models import CloudInstanceInfo

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


class CloudJobRunner(JobRunnerMixin, BaseRunner[Job]):
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
        executor: JobExecutor | MatrixExecutor | None = None,
        cloud_executor: CloudExecutor | None = None,
    ):
        self._job_executor = executor or JobExecutor()
        self._cloud_executor = cloud_executor or CloudExecutor()
        super().__init__(
            job,
            ctx,
            parent,
            parent.registry,
            executor=self._job_executor,
        )
        self._cloud_config: CloudConfig = cloud_config or job.cloud  # type: ignore[assignment]
        self._provider: CloudProvider | None = None
        self._instance: CloudInstanceInfo | None = None
        self._remote_runner: Any = None  # PostSSH or PostWinRM
        self._work_dir: str | None = None
        self._is_fleet_child: bool = False  # Set by CloudFleetRunner for fleet children
        self._cached_python: str | None = None  # Cached across steps on same VPS
        self._failure_cleanup_done: bool = False

    async def run(self, *args, **kwargs):
        """Override to ensure VPS destruction on failure."""
        result = await super().run(*args, **kwargs)
        if result.status == RunnerStatus.FAILED and not self._failure_cleanup_done:
            await self._on_failure_cleanup()
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
        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)

        # Resolve cloud profile
        cfg = self._cloud_config
        if isinstance(cfg, str):
            from ofx.models.cloud import parse_cloud_field

            cfg = parse_cloud_field(cfg)
        if cfg is None:
            raise RuntimeError(
                f"Cloud config is required for job '{self.model.jid}'. "
                "Set 'cloud:' on the job or use a cloud profile."
            )

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

        # Check run_if conditions (shared with JobRunner via mixin)
        self._check_dependencies_and_run_if()

        # Provision VPS or connect to static host
        self._log_info(
            f"Provisioning cloud instance for '{self.model.name or self.model.jid}' "
            f"(provider={resolved.provider})"
        )
        try:
            await self._provision_instance(resolved)
        except Exception:
            # Emergency cleanup: destroy partially-provisioned instance
            await self._emergency_deprovision()
            raise

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
        await self._cloud_executor.provision_instance(self, cfg)

    def _build_provider_kwargs(self, cfg: CloudConfig) -> dict[str, Any]:
        """Build kwargs for CloudProviderRegistry.create()."""
        from ofx.cloud.runtime import build_provider_kwargs

        return build_provider_kwargs(cfg)

    def _create_remote_runner(self, cfg: CloudConfig):
        """Create PostSSH or PostWinRM instance for the provisioned instance."""
        return self._cloud_executor.build_remote_runner(self, cfg)

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
        await self._cloud_executor.dispatch_remote_steps(
            self,
            matrix_combo,
            suffix=suffix,
        )

    # ------------------------------------------------------------------
    # Post-run: collect outputs, destroy
    # ------------------------------------------------------------------

    async def _post_run(self) -> None:
        await self._save_job_results()

        await self._download_outputs()
        await self._destroy_instance()
        await self._cleanup_remote()

    async def _download_outputs(self) -> None:
        """Download output files from remote VPS."""
        await self._cloud_executor.download_outputs(self)

    async def _destroy_instance(self) -> None:
        """Destroy cloud instance if auto_destroy is enabled."""
        await self._cloud_executor.destroy_instance(self)

    async def _emergency_deprovision(self) -> None:
        """Best-effort cleanup of a partially-provisioned instance."""
        await self._cloud_executor.emergency_deprovision(self)

    async def _on_failure_cleanup(self) -> None:
        """Handle failure: salvage outputs, ensure VPS destruction."""
        self._failure_cleanup_done = True
        try:
            await self._download_outputs()
        except Exception as e:
            self._log_warning(f"Output salvage on failure failed: {e}")
        await self._destroy_instance()
        await self._cleanup_remote()

    async def _cleanup_remote(self) -> None:
        """Clean up remote working directory and runner resources."""
        await self._cloud_executor.cleanup_remote(self)


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
        remote_env_updates: dict[str, str] = {}
        remote_var_updates: dict[str, Any] = {}
        for k, v in fleet_vars.items():
            if k == "fleet_input_file":
                continue
            remote_key = f"REMOTE_{k.upper()}"
            if isinstance(v, list):
                str_val = "\n".join(str(x) for x in v)
            else:
                str_val = str(v)
            remote_env_updates[remote_key] = str_val
            remote_var_updates[f"remote_{k}"] = v

        if remote_env_updates:
            self.ctx = RunnerContextBuilder(self.ctx).with_env(remote_env_updates)
        if remote_var_updates:
            self.ctx = RunnerContextBuilder(self.ctx).with_vars(remote_var_updates)

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
            self.ctx = RunnerContextBuilder(self.ctx).with_env(
                {"REMOTE_FLEET_INPUT_FILE": remote_path}
            )
            self.ctx = RunnerContextBuilder(self.ctx).with_vars(
                {"remote_fleet_input_file": remote_path}
            )
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
        prefix = LogContext(model_name=workflow_name, model_jid=self.model.jid).prefix
        msg = f"{prefix} [cloud] › {message_str}" if prefix else f"[cloud] › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def remote_work_dir(self) -> str | None:
        return self._work_dir
