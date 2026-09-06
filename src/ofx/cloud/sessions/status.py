"""Session status polling: local/cloud liveness probes, markers, and logs."""

from __future__ import annotations

import logging
import os
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.models import Session, SessionStatus, SessionTarget
from ofx.cloud.sessions.submit import _cloud_connection_settings

logger = logging.getLogger("ofx")

_DONE_MARKER = "__TASK_OK__"
_FAIL_MARKER = "__TASK_ERR__"

_INITIAL_POLL_INTERVAL = 10.0
_MAX_POLL_INTERVAL = 120.0
_POLL_BACKOFF_FACTOR = 1.5
_MAX_CONSECUTIVE_FAILURES = 10
_SSH_COMMAND_TIMEOUT = 30

class StatusMixin:
    async def status(self, session_id: str) -> Session:
        """Check the current status of a session.

        For running sessions, probes the remote/local PID and log markers.
        """
        session = self.store.load(session_id)

        if not session.is_running():
            return session

        if session.target == SessionTarget.LOCAL:
            session = self._check_local_status(session)
        else:
            session = await self._check_cloud_status(session)

        self.store.save(session)
        return session
    def _check_local_status(self, session: Session) -> Session:
        """Check if a local background process is still alive."""
        if session.remote_pid is None:
            return self._mark_failed(session, error="No PID recorded")

        try:
            os.kill(session.remote_pid, 0)
        except (ProcessLookupError, PermissionError):
            alive = False
        else:
            try:
                with open(f"/proc/{session.remote_pid}/status") as fh:
                    alive = True
                    for line in fh:
                        if line.startswith("State:"):
                            alive = "Z" not in line
                            break
            except (FileNotFoundError, PermissionError, OSError):
                alive = True

        log_path = Path(session.remote_log_file)
        if not log_path.exists():
            marker = None
        else:
            try:
                log_text = log_path.read_text(errors="replace")
                if _DONE_MARKER in log_text:
                    marker = _DONE_MARKER
                elif _FAIL_MARKER in log_text:
                    marker = _FAIL_MARKER
                else:
                    marker = None
            except Exception as exc:
                logger.debug("Failed to read status file %s: %s", log_path, exc)
                marker = None

        marker_status = self._status_from_marker(session, marker)
        if marker_status is not None:
            return marker_status
        if alive:
            return session
        return self._mark_failed(
            session, error="Process exited without success marker"
        )
    async def _check_cloud_status(self, session: Session) -> Session:
        """SSH in and check PID + log markers on a cloud VPS.

        Tracks consecutive connection failures per session.  After
        *_MAX_CONSECUTIVE_FAILURES* the session is marked ``UNREACHABLE``.
        On a successful probe the failure counter resets to zero.
        """
        self._ensure_poll_failures()

        if session.remote_pid is None:
            return self._check_cloud_status_without_pid(session)
        return self._check_cloud_status_with_pid(session)
    def _check_cloud_status_without_pid(self, session: Session) -> Session:
        def _probe(remote: Any) -> Session:
            tail_cmd = (
                f'powershell "Get-Content -Tail 5 {session.remote_log_file}"'
                if session.os_type == "windows"
                else f"tail -5 {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
            )
            log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
            marker = None
            if _DONE_MARKER in log_tail:
                marker = _DONE_MARKER
            elif _FAIL_MARKER in log_tail:
                marker = _FAIL_MARKER

            self._reset_poll_failures(session.id)

            marker_status = self._status_from_marker(session, marker)
            if marker_status is not None:
                return marker_status
            if (
                session.os_type != "windows"
                and session.remote_launcher == "tmux"
                and session.remote_tmux_session
            ):
                tmux_alive = remote.run(
                    f"tmux has-session -t {shlex.quote(str(session.remote_tmux_session))} "
                    "2>/dev/null && echo alive || echo dead",
                    timeout=_SSH_COMMAND_TIMEOUT,
                )
                if "alive" in tmux_alive.strip().lower():
                    return session
            return session

        return self._with_cloud_remote_probe(
            session,
            reconnect_error=(
                "Status check (no-pid) failed for %s "
                "(attempt %d, next backoff %.1fs): %s"
            ),
            reconnect_args=(session.id,),
            probe_error=(
                "Status check (no-pid) failed for %s "
                "(attempt %d, next backoff %.1fs): %s"
            ),
            probe_args=(session.id,),
            probe=_probe,
        )
    def _check_cloud_status_with_pid(self, session: Session) -> Session:
        def _probe(remote: Any) -> Session:
            if session.os_type == "windows":
                check_cmd = (
                    f'powershell "(Get-Process -Id {session.remote_pid} '
                    f'-ErrorAction SilentlyContinue) -ne $null"'
                )
            elif session.remote_launcher == "tmux" and session.remote_tmux_session:
                check_cmd = (
                    f"tmux has-session -t {shlex.quote(str(session.remote_tmux_session))} 2>/dev/null "
                    "&& echo alive || echo dead"
                )
            else:
                check_cmd = (
                    f"kill -0 {session.remote_pid} 2>/dev/null && echo alive || echo dead"
                )
            output = remote.run(check_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip().lower()
            alive = "alive" in output or "true" in output
            tail_cmd = (
                f'powershell "Get-Content -Tail 5 {session.remote_log_file}"'
                if session.os_type == "windows"
                else f"tail -5 {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
            )
            log_tail = remote.run(tail_cmd, timeout=_SSH_COMMAND_TIMEOUT).strip()
            marker = None
            if _DONE_MARKER in log_tail:
                marker = _DONE_MARKER
            elif _FAIL_MARKER in log_tail:
                marker = _FAIL_MARKER

            self._reset_poll_failures(session.id)
            marker_status = self._status_from_marker(session, marker)
            if marker_status is not None:
                return marker_status
            if alive:
                return session
            return self._mark_failed(
                session, error="Process exited without success marker"
            )

        return self._with_cloud_remote_probe(
            session,
            reconnect_error=(
                "Cannot reconnect to %s (attempt %d, next backoff %.1fs): %s"
            ),
            reconnect_args=(session.instance_ip,),
            probe_error=(
                "Status check failed for %s (attempt %d, next backoff %.1fs): %s"
            ),
            probe_args=(session.id,),
            probe=_probe,
        )
    def _with_cloud_remote_probe(
        self,
        session: Session,
        *,
        reconnect_error: str,
        reconnect_args: tuple[Any, ...],
        probe_error: str,
        probe_args: tuple[Any, ...],
        probe: Callable[[Any], Session],
    ) -> Session:
        try:
            remote = self._reconnect(session)
        except Exception as exc:
            return self._poll_failure_result(
                session,
                exc,
                debug_message=reconnect_error,
                debug_args=reconnect_args,
            )

        try:
            return probe(remote)
        except Exception as exc:
            return self._poll_failure_result(
                session,
                exc,
                debug_message=probe_error,
                debug_args=probe_args,
            )
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()
    def _with_reconnected_remote(
        self,
        session: Session,
        operation: Callable[[Any], Any],
    ) -> Any:
        remote = self._reconnect(session)
        try:
            return operation(remote)
        finally:
            if hasattr(remote, "cleanup"):
                remote.cleanup()
    def _reconnect(self, session: Session) -> Any:
        """Create a PostSSH or PostWinRM to reconnect to a session's host."""
        from ofx.cloud.runtime import create_remote_runner
        from ofx.models.cloud import CloudConfig

        connection = _cloud_connection_settings(
            os_type=session.os_type or "linux",
            ssh_user=session.ssh_user or "root",
            ssh_port=session.ssh_port or 22,
            ssh_key=session.ssh_key or "",
            ssh_password=session.ssh_password or "",
            winrm_user=session.winrm_user or session.ssh_user or "Administrator",
            winrm_password=session.ssh_password or "",
            winrm_ssl=session.winrm_ssl or False,
            winrm_port=session.winrm_port,
            winrm_transport=session.winrm_transport or "ntlm",
        )
        cfg = CloudConfig(
            provider=session.cloud_provider or "static",
            os=connection["os_type"],
            connection_type=connection["connection_type"],
            ssh_user=connection["ssh_user"],
            ssh_port=connection["ssh_port"],
            ssh_key=connection["ssh_key"],
            ssh_password=connection["ssh_password"],
            winrm_user=connection["winrm_user"],
            winrm_password=connection["winrm_password"],
            winrm_ssl=connection["winrm_ssl"],
            winrm_port=connection["winrm_port"],
            winrm_transport=connection["winrm_transport"],
        )
        return create_remote_runner(cfg, session.instance_ip, max_retries=2)
    def _status_from_marker(
        self,
        session: Session,
        marker: str | None,
        *,
        missing_error: str = "",
    ) -> Session | None:
        if marker == _DONE_MARKER:
            return self._mark_completed(session)
        if marker == _FAIL_MARKER:
            return self._mark_failed(session)
        if missing_error:
            return self._mark_failed(session, error=missing_error)
        return None
    def _reset_poll_failures(self, session_id: str) -> None:
        self._poll_failures[session_id] = 0
    def _ensure_poll_failures(self) -> None:
        if not hasattr(self, "_poll_failures"):
            self._poll_failures = {}
    def _poll_failure_result(
        self,
        session: Session,
        exc: Exception,
        *,
        debug_message: str,
        debug_args: tuple[Any, ...],
    ) -> Session:
        count = self._poll_failures.get(session.id, 0) + 1
        self._poll_failures[session.id] = count
        backoff = min(
            _INITIAL_POLL_INTERVAL * (_POLL_BACKOFF_FACTOR**count),
            _MAX_POLL_INTERVAL,
        )
        if count >= _MAX_CONSECUTIVE_FAILURES:
            logger.warning(
                "Session %s unreachable after %d consecutive failures",
                session.id,
                count,
            )
            return session.model_copy(
                update={
                    "status": SessionStatus.UNREACHABLE,
                    "error": (
                        f"Unreachable after {count} consecutive poll failures: {exc}"
                    ),
                }
            )

        logger.debug(debug_message, *debug_args, count, backoff, exc)
        return session
    async def logs(self, session_id: str, tail: int = 50, follow: bool = False) -> str:
        """Retrieve log output from a session.

        Args:
            session_id: Session ID.
            tail: Number of lines to return.
            follow: If True, streams (blocks) — only for local sessions.

        Returns:
            Log content as a string.
        """
        session = self.store.load(session_id)

        if session.target == SessionTarget.LOCAL:
            log_path = Path(session.remote_log_file)
            if not log_path.exists():
                return "(no log file yet)"
            try:
                return "\n".join(
                    log_path.read_text(errors="replace").splitlines()[-tail:]
                )
            except Exception:
                return "(cannot read log)"

        try:
            def _read_remote_logs(remote: Any) -> str:
                cmd = (
                    f'powershell "Get-Content -Tail {tail} {session.remote_log_file}"'
                    if session.os_type == "windows"
                    else f"tail -{tail} {shlex.quote(str(session.remote_log_file))} 2>/dev/null"
                )
                return remote.run(cmd, timeout=30)

            return self._with_reconnected_remote(session, _read_remote_logs)
        except Exception as exc:
            return f"(cannot retrieve logs: {exc})"
