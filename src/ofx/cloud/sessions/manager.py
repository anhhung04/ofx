"""Session lifecycle manager — submit, status, fetch, cancel, destroy.

Orchestrates both **local** (background subprocess) and **cloud** (VPS) sessions.
Responsibilities are split into mixins: submit.py, status.py, results.py.
"""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import shlex
import signal
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.results import ResultsMixin
from ofx.cloud.sessions.status import _SSH_COMMAND_TIMEOUT, StatusMixin
from ofx.cloud.sessions.store import SessionStore
from ofx.cloud.sessions.submit import SubmitMixin
from ofx.runner.profile_env import build_profile_env_overrides
from ofx.utils.file_cleanup import remove_tree

logger = logging.getLogger("ofx")

class SessionManager(SubmitMixin, StatusMixin, ResultsMixin):
    """High-level API for detached session lifecycle.

    Usage::

        mgr = SessionManager()
        session = await mgr.submit("scan.yml", target=SessionTarget.LOCAL)
        info = await mgr.status(session.id)
        await mgr.fetch(session.id, passphrase="s3cr3t")
    """

    def __init__(self, store: SessionStore | None = None):
        self.store = store or SessionStore()
        self._poll_failures: dict[str, int] = {}
    async def submit(
        self,
        workflow_file: str,
        *,
        job_id: str = "",
        target: SessionTarget = SessionTarget.LOCAL,
        cloud_profile: str = "",
        inputs: dict[str, Any] | None = None,
        name: str = "",
        env: dict[str, str] | None = None,
        tags: dict[str, str] | None = None,
        project: str = "",
    ) -> Session:
        """Submit a workflow as a detached session.

        Args:
            workflow_file: Workflow path or name.
            job_id: Specific job ID to run (empty = full workflow).
            target: LOCAL or CLOUD.
            cloud_profile: Cloud profile slug (for CLOUD target).
            inputs: Workflow inputs.
            name: Human-friendly session name.
            env: Extra environment variables.
            tags: Arbitrary tags.
            project: Project name to associate with this session.

        Returns:
            The created Session (status = RUNNING after this returns).
        """
        session_id = _secrets.token_hex(4)

        from ofx.settings import get_workflow_search_dirs
        from ofx.utils.workflow_utils import find_workflow

        workflow = find_workflow(workflow_file, tuple(get_workflow_search_dirs()))
        session_steps, resolved_job_id = self._resolve_session_steps(workflow, job_id)
        workflow_name = workflow.name or Path(workflow_file).stem
        profile_name = workflow.defaults.profile or ""
        workflow_profile = None
        if profile_name:
            from ofx.profiles.manager import get_profile_manager

            workflow_profile = get_profile_manager().resolve_or_default(profile_name)
        if workflow_profile is not None and getattr(workflow_profile.time_window, "enabled", False):
            from ofx.profiles.time_window import check_time_window

            time_window_result = check_time_window(workflow_profile.time_window)
            if not time_window_result["allowed"]:
                raise RuntimeError(
                    f"Session submit aborted: {time_window_result['message']}"
                )
            if time_window_result["message"]:
                logger.warning(time_window_result["message"])

        merged_env = dict(env or {})
        if workflow_profile is not None:
            merged_env = build_profile_env_overrides(workflow_profile) | merged_env

        session = Session(
            id=session_id,
            name=name or workflow_name,
            workflow_file=workflow_file,
            job_id=resolved_job_id,
            target=target,
            status=SessionStatus.PROVISIONING,
            cloud_profile=cloud_profile,
            inputs=inputs or {},
            tags=tags or {},
            project=project,
        )

        self.store.save(session)

        if target == SessionTarget.LOCAL:
            session = await self._submit_local(
                session,
                session_steps,
                merged_env,
                workflow_profile,
                workflow_dir=workflow.workflow_path.parent if workflow.workflow_path else None,
                workflow_name=workflow_name,
            )
        else:
            session = await self._submit_cloud(
                session,
                session_steps,
                merged_env,
                cloud_profile,
                workflow_profile,
                workflow_dir=workflow.workflow_path.parent if workflow.workflow_path else None,
                workflow_name=workflow_name,
            )

        return session
    async def cancel(self, session_id: str) -> Session:
        """Kill the running process and mark session as canceled."""
        session = self.store.load(session_id)

        if not session.is_running():
            return session

        if session.target == SessionTarget.LOCAL:
            self._cancel_local_execution(session)
        else:
            try:
                self._with_reconnected_remote(
                    session,
                    lambda remote: (
                        remote.run(
                            f'powershell "Stop-Process -Id {session.remote_pid} -Force -ErrorAction SilentlyContinue"',
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.os_type == "windows"
                        else remote.run(
                            f"tmux kill-session -t {shlex.quote(str(session.remote_tmux_session))} 2>/dev/null || true",
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.remote_launcher == "tmux" and session.remote_tmux_session
                        else remote.run(
                            f"kill {session.remote_pid} 2>/dev/null; sleep 1; kill -9 {session.remote_pid} 2>/dev/null",
                            timeout=_SSH_COMMAND_TIMEOUT,
                        )
                        if session.remote_pid
                        else None
                    ),
                )
            except Exception as exc:
                logger.debug("Cancel failed for %s: %s", session.id, exc)

        return self._save_session(
            session,
            self._finished_session_update(SessionStatus.CANCELED),
        )
    async def destroy(self, session_id: str, force: bool = False) -> Session:
        """Destroy the VPS for a cloud session. Cancel first if still running.

        For local sessions, just cleans up the workspace.
        """
        session = self.store.load(session_id)

        if session.is_running():
            if force:
                session = await self.cancel(session_id)
            else:
                raise RuntimeError(
                    f"Session {session_id} is still running. Use --force to cancel and destroy."
                )

        remove_tree(
            Path(session.remote_work_dir)
            if session.target == SessionTarget.LOCAL and session.remote_work_dir
            else None,
            on_error=logger.warning,
            label="session workspace",
        )

        if session.target == SessionTarget.CLOUD and session.instance_id:
            session = await self._destroy_session_instance(
                session,
                clear_instance_fields=False,
                warning_message="Failed to destroy session %s instance %s: %s",
            )

        return self._save_session(
            session,
            self._finished_session_update(
                SessionStatus.DESTROYED,
                finished_at=session.finished_at,
            ),
        )
    async def _destroy_session_instance(
        self,
        session: Session,
        *,
        clear_instance_fields: bool,
        warning_message: str,
    ) -> Session:
        if session.target != SessionTarget.CLOUD or not session.instance_id:
            return session
        if (session.cloud_provider or "static") == "static":
            return session

        try:
            from ofx.cloud import CloudProviderRegistry
            from ofx.cloud.config import get_cloud_profile_manager
            from ofx.cloud.runtime import build_provider_kwargs
            from ofx.models.cloud import CloudConfig

            resolved = get_cloud_profile_manager().resolve(
                CloudConfig(profile=session.cloud_profile)
                if session.cloud_profile
                else CloudConfig()
            )
            provider = CloudProviderRegistry.create(
                session.cloud_provider or getattr(resolved, "provider", None) or "static",
                **build_provider_kwargs(resolved),
            )
            await provider.destroy_instance(session.instance_id)
            if clear_instance_fields:
                return self._save_session(
                    session,
                    {"instance_id": "", "instance_ip": ""},
                )
            return session
        except Exception as exc:
            logger.warning(warning_message, session.id, session.instance_id, exc)
            return session
    def _save_session(self, session: Session, update: dict) -> Session:
        """Update session fields and persist to store."""
        session = session.model_copy(update=update)
        self.store.save(session)
        return session
    def _mark_completed(self, session: Session) -> Session:
        return session.model_copy(
            update=self._finished_session_update(SessionStatus.COMPLETED)
        )
    def _mark_failed(self, session: Session, *, error: str = "") -> Session:
        return session.model_copy(
            update=self._finished_session_update(
                SessionStatus.FAILED,
                error=error,
            )
        )
    @staticmethod
    def _finished_session_update(
        status: SessionStatus,
        *,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        update: dict[str, Any] = {
            "status": status,
            "finished_at": finished_at or datetime.now(UTC),
        }
        if error is not None:
            update["error"] = error
        return update
    @staticmethod
    def _cancel_local_execution(session: Session) -> None:
        if session.remote_pid is None:
            return

        pid = session.remote_pid
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            with suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
            pgid = None
        else:
            # Give processes a moment to exit gracefully, then SIGKILL
            import time
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    os.killpg(pgid, 0)
                except (OSError, ProcessLookupError):
                    break
                time.sleep(0.1)
            else:
                with suppress(OSError, ProcessLookupError):
                    os.killpg(pgid, signal.SIGKILL)

        # Reap all zombies in the process group
        if pgid is not None:
            try:
                while True:
                    wpid, _status = os.waitpid(-pgid, os.WNOHANG)
                    if wpid == 0:
                        break
            except ChildProcessError:
                pass
        # Fallback: reap the direct child
        try:
            while True:
                wpid, _status = os.waitpid(pid, os.WNOHANG)
                if wpid == 0:
                    break
        except ChildProcessError:
            pass
    def _resolve_session_steps(
        self, workflow: Any, job_id: str
    ) -> tuple[list[Any], str]:
        """Resolve steps to execute for a session.

        When ``job_id`` is provided, only that job's steps are used.
        Otherwise, all workflow jobs are linearized by dependency stage order.
        """
        jobs = workflow.jobs
        if not isinstance(jobs, dict):
            raise ValueError("Workflow jobs must be a mapping of job_id -> job")
        if not jobs:
            raise ValueError("Workflow has no jobs")

        if job_id:
            job = jobs.get(job_id)
            if job is None:
                raise ValueError(f"Job '{job_id}' not found in workflow")
            return list(job.steps), job.jid

        from ofx.runner.workflow_scheduler import WorkflowScheduler

        schedule = WorkflowScheduler(jobs).plan().schedule
        selected_steps: list[Any] = []
        for stage in schedule:
            for staged_job_id in stage:
                job = jobs[staged_job_id]
                for idx, step in enumerate(job.steps):
                    base_name = step.name or f"step_{idx}"
                    selected_steps.append(
                        step.model_copy(update={"name": f"{job.jid}::{base_name}"})
                    )
        return selected_steps, ""
