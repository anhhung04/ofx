"""Persistent session store backed by JSON files in ~/.ofx/sessions/."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.models import Session, SessionStatus
from ofx.utils.file_cleanup import remove_tree

logger = logging.getLogger("ofx")

class SessionStore:
    """CRUD operations for session metadata stored on disk.

    Layout:
        ~/.ofx/sessions/
            {session_id}/
                session.json    — serialised Session model
                results/        — fetched output files
                results.enc     — encrypted results archive (optional)
    """

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            from ofx.settings import BASE_DATA_DIR

            base_dir = BASE_DATA_DIR / "sessions"
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def save(self, session: Session) -> Path:
        """Persist a session to disk (create or overwrite)."""
        path = self._session_file(session.id, ensure_dir=True)
        self._write_json(path, session.model_dump(mode="json"))
        return path

    def load(self, session_id: str) -> Session:
        """Load a session by ID. Raises FileNotFoundError if missing."""
        path = self._session_file(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")
        return Session(**self._read_json(path))

    def exists(self, session_id: str) -> bool:
        return self._session_file(session_id).exists()

    def delete(self, session_id: str) -> None:
        """Remove all data for a session."""
        remove_tree(
            self.session_dir(session_id),
            on_error=logger.warning,
            label="session directory",
        )

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        **extra_fields: Any,
    ) -> Session:
        """Atomically update session status and optional extra fields.

        Uses an exclusive file lock for the entire read-modify-write cycle
        to prevent concurrent callers from losing each other's updates.
        """
        path = self._session_file(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")

        with self._locked_fd(path, os.O_RDWR) as fd:
            data = self._read_locked_json_fd(fd)

            data["status"] = status.value if hasattr(status, "value") else status
            data.update(extra_fields)

            self._write_locked_json_fd(fd, data)
            return Session(**data)

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        target: str | None = None,
        project: str | None = None,
    ) -> list[Session]:
        """List all sessions, optionally filtered by status, target, or project."""
        return [
            session
            for session in self._iter_sessions()
            if self._session_matches_filters(
                session,
                status=status,
                target=target,
                project=project,
            )
        ]

    def list_by_fleet_group(self, fleet_group_id: str) -> list[Session]:
        """Return all sessions belonging to a fleet group, sorted by fleet_index."""
        sessions = [
            s for s in self.list_sessions() if s.fleet_group_id == fleet_group_id
        ]
        sessions.sort(key=lambda s: s.fleet_index)
        return sessions

    def session_dir(self, session_id: str) -> Path:
        """Public accessor for a session's directory."""
        return self._base_dir / session_id

    def results_dir(self, session_id: str) -> Path:
        d = self.session_dir(session_id) / "results"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def clean(
        self,
        older_than_seconds: int | None = None,
        statuses: list[SessionStatus] | None = None,
    ) -> int:
        """Remove sessions matching criteria. Returns count deleted."""
        now = datetime.now(UTC)
        removed = 0
        for session in self._iter_sessions():
            if not self._should_remove_session(
                session,
                now=now,
                older_than_seconds=older_than_seconds,
                statuses=statuses,
            ):
                continue
            self.delete(session.id)
            removed += 1
        return removed

    def _session_file(self, session_id: str, *, ensure_dir: bool = False) -> Path:
        session_dir = self.session_dir(session_id)
        if ensure_dir:
            session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "session.json"

    def _iter_session_files(self):
        for child in sorted(self._base_dir.iterdir()):
            meta_file = child / "session.json"
            if child.is_dir() and meta_file.exists():
                yield meta_file

    def _iter_sessions(self) -> Iterator[Session]:
        if not self._base_dir.exists():
            return

        for meta_file in self._iter_session_files():
            try:
                yield Session(**self._read_json(meta_file))
            except Exception as exc:
                logger.debug(
                    "Skipping corrupt session %s: %s",
                    meta_file.parent.name,
                    exc,
                )

    @staticmethod
    def _session_matches_filters(
        session: Session,
        *,
        status: SessionStatus | None,
        target: str | None,
        project: str | None,
    ) -> bool:
        if status and session.status != status:
            return False
        if target and session.target.value != target:
            return False
        if project and session.project != project:
            return False
        return True

    @staticmethod
    def _should_remove_session(
        session: Session,
        *,
        now: datetime,
        older_than_seconds: int | None,
        statuses: list[SessionStatus] | None,
    ) -> bool:
        if statuses and session.status not in statuses:
            return False
        if older_than_seconds is None:
            return True
        age = (now - session.started_at).total_seconds()
        return age >= older_than_seconds

    @staticmethod
    def _read_locked_json_fd(fd: int) -> dict[str, Any]:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 10_000_000)
        return json.loads(raw)

    @staticmethod
    def _write_locked_json_fd(fd: int, data: dict[str, Any]) -> None:
        content = json.dumps(data, indent=2, default=str).encode()
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, content)
        os.fsync(fd)

    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON atomically: lock before truncate to prevent races."""
        with self._locked_fd(path, os.O_WRONLY | os.O_CREAT) as fd:
            self._write_locked_json_fd(fd, data)

    @staticmethod
    @contextmanager
    def _locked_fd(path: Path, flags: int) -> Generator[int]:
        fd = os.open(str(path), flags, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield fd
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_json(self, path: Path) -> dict:
        with open(path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
