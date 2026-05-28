"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.executors.cloud import CloudExecutor
from ofx.runner.logging import bubble_tagged_log
from ofx.runner.runner import BaseRunner

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


def cloud_job_log_prefix(
    job_id: str,
    *,
    workflow_name: str = "",
    fleet_name: str = "",
    quote_job_id: bool = False,
) -> str:
    """Build a consistent cloud runner log prefix."""
    prefix = f"'{job_id}'" if quote_job_id else f"job={job_id}"
    if workflow_name:
        prefix = f"name={workflow_name} | {prefix}"
    if fleet_name:
        prefix = f"{prefix} [{fleet_name}]"
    return prefix


class CloudJobRunner(BaseRunner[Job]):
    """Runs a job on a cloud VPS (or static remote host).

    The base runner delegates lifecycle hooks to CloudExecutor, which handles
    provisioning, remote step dispatch, output collection, and cleanup.
    """

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: BaseRunner[Workflow],
        cloud_config: CloudConfig | None = None,
        cloud_executor: CloudExecutor | None = None,
    ):
        self._cloud_executor = cloud_executor or CloudExecutor()
        super().__init__(
            job,
            ctx,
            parent,
            parent.registry,
            executor=self._cloud_executor,
        )
        self._cloud_config: CloudConfig = cloud_config or job.cloud  # type: ignore[assignment]
        self._provider: CloudProvider | None = None
        self._instance: CloudInstanceInfo | None = None
        self._remote_runner: Any = None  # PostSSH or PostWinRM
        self._work_dir: str | None = None
        self._is_fleet_child: bool = False  # Set by CloudFleetRunner for fleet children
        self._cached_python: str | None = None  # Cached across steps on same VPS

    @staticmethod
    def _fleet_runtime_updates(
        fleet_vars: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build remote fleet env/vars from local fleet metadata."""
        remote_env_updates: dict[str, str] = {}
        remote_var_updates: dict[str, Any] = {}
        for key, value in fleet_vars.items():
            if key == "fleet_input_file":
                continue
            remote_key = f"REMOTE_{key.upper()}"
            if isinstance(value, list):
                remote_env_updates[remote_key] = "\n".join(str(item) for item in value)
            else:
                remote_env_updates[remote_key] = str(value)
            remote_var_updates[f"remote_{key}"] = value
        return remote_env_updates, remote_var_updates

    @staticmethod
    def _remote_fleet_input_path(work_dir: str, *, is_windows: bool) -> str:
        if is_windows:
            return f"{work_dir}\\fleet_targets.txt"
        return f"{work_dir}/fleet_targets.txt"

    def _apply_fleet_runtime_updates(self, fleet_vars: dict[str, Any]) -> None:
        """Inject fleet metadata into the runner context."""
        remote_env_updates, remote_var_updates = self._fleet_runtime_updates(fleet_vars)
        if remote_env_updates or remote_var_updates:
            self.update_env_and_vars(
                remote_env_updates,
                remote_var_updates,
            )

    def _apply_remote_fleet_input_path(self, remote_path: str) -> None:
        """Record the uploaded remote fleet input path in env and vars."""
        self.update_env_and_vars(
            {"REMOTE_FLEET_INPUT_FILE": remote_path},
            {"remote_fleet_input_file": remote_path},
        )

    async def _upload_fleet_input(self) -> None:
        """Upload the local fleet chunk file to the remote host.

        When this CloudJobRunner is spawned by CloudMatrixJobRunner with
        fleet expansion, ``ctx.vars["fleet"]["fleet_input_file"]`` points to a
        local temp file.  We upload it and set explicit remote env vars.
        """
        fleet_vars = self.ctx.vars.get("fleet", {})
        local_path = fleet_vars.get("fleet_input_file", "")

        self._apply_fleet_runtime_updates(fleet_vars)

        if not local_path:
            return

        local = Path(local_path)
        if not local.is_file():
            return

        if not self._remote_runner or not self._work_dir:
            return

        is_windows = bool(
            self._cloud_config and self._cloud_config.connection_type == "winrm"
        )
        remote_path = self._remote_fleet_input_path(
            self._work_dir,
            is_windows=is_windows,
        )

        try:
            await asyncio.to_thread(self._remote_runner.upload, str(local), remote_path)
            self._apply_remote_fleet_input_path(remote_path)
            self._log_info(f"Uploaded fleet input → {remote_path}")
        except Exception as e:
            raise RuntimeError(
                f"Failed to upload fleet input file '{local}' → '{remote_path}': {e}"
            ) from e

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _produce_log(self, message: Any) -> str:
        workflow_name = ""
        if self.parent and getattr(self.parent, "model", None):
            workflow_name = getattr(self.parent.model, "name", "") or ""
        return bubble_tagged_log(
            self.parent,
            message,
            prefix=cloud_job_log_prefix(
                self.model.jid,
                workflow_name=workflow_name,
            ),
            tags=("cloud",),
        )

    @property
    def remote_work_dir(self) -> str | None:
        return self._work_dir

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    async def dispatch_remote_steps(
        self,
        matrix_combo: dict[str, Any] | None = None,
        suffix: str = "",
    ) -> None:
        """Dispatch this job's steps through the composed cloud executor."""
        await self._cloud_executor.dispatch_remote_steps(self, matrix_combo, suffix)

    async def destroy_instance(self) -> None:
        """Destroy the provisioned cloud instance when policy allows it."""
        await self._cloud_executor.destroy_instance(self)
