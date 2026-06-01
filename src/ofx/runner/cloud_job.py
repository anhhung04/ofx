"""Cloud job runner — provisions VPS, runs job remotely, destroys on completion."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.cloud.runtime import is_windows_config, remote_join
from ofx.models.cloud import CloudConfig
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.context import RunContext
from ofx.runner.executors.cloud import CloudExecutor
from ofx.runner.metadata import ModelContext
from ofx.runner.runner import Runner

if TYPE_CHECKING:
    from ofx.cloud.base import CloudProvider
    from ofx.cloud.models import CloudInstanceInfo

class CloudJobRunner(Runner[Job]):
    """Runs a job on a cloud VPS (or static remote host).

    The base runner delegates lifecycle hooks to CloudExecutor, which handles
    provisioning, remote step dispatch, output collection, and cleanup.
    """

    def __init__(
        self,
        job: Job,
        ctx: RunContext,
        parent: Runner[Workflow],
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
        self._cached_python: str | None = None  # Cached across steps on same VPS

    async def _upload_fleet_input(self) -> None:
        """Upload the local fleet chunk file to the remote host.

        When this CloudJobRunner is spawned by CloudMatrixJobRunner with
        fleet expansion, ``ctx.vars["fleet"]["fleet_input_file"]`` points to a
        local temp file.  We upload it and set explicit remote env vars.
        """
        fleet_vars = self.ctx.vars.get("fleet", {})
        remote_env_updates: dict[str, str] = {}
        remote_var_updates: dict[str, Any] = {}
        for key, value in fleet_vars.items():
            if key == "fleet_input_file":
                continue
            remote_env_updates[f"REMOTE_{key.upper()}"] = (
                "\n".join(str(item) for item in value)
                if isinstance(value, list)
                else str(value)
            )
            remote_var_updates[f"remote_{key}"] = value
        if remote_env_updates or remote_var_updates:
            self.update_env_and_vars(remote_env_updates, remote_var_updates)

        local_path = str(fleet_vars.get("fleet_input_file", "") or "")
        local = Path(local_path) if local_path else None
        if not (local and local.is_file() and self._remote_runner and self._work_dir):
            return

        remote_path = remote_join(
            self._work_dir,
            "fleet_targets.txt",
            is_windows=bool(self._cloud_config and is_windows_config(self._cloud_config)),
        )

        try:
            await asyncio.to_thread(self._remote_runner.upload, str(local), remote_path)
            self.update_env_and_vars(
                {"REMOTE_FLEET_INPUT_FILE": remote_path},
                {"remote_fleet_input_file": remote_path},
            )
            self._log_info(f"Uploaded fleet input → {remote_path}")
        except Exception as e:
            raise RuntimeError(
                f"Failed to upload fleet input file '{local}' → '{remote_path}': {e}"
            ) from e

    def _produce_log(self, message: Any) -> str:
        workflow_name = ModelContext.from_model(getattr(self.parent, "model", None)).name or ""
        prefix = f"name={workflow_name} | job={self.model.jid}" if workflow_name else f"job={self.model.jid}"
        formatted = f"{prefix} [cloud] › {message}"
        if self.parent is not None:
            return self.parent._produce_log(formatted)
        return formatted
