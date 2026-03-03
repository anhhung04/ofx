"""Persistent session store backed by JSON files in ~/.ofx/sessions/."""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.cloud.sessions.models import Session, SessionStatus

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

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, session: Session) -> Path:
        """Persist a session to disk (create or overwrite)."""
        session_dir = self._session_dir(session.id)
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / "session.json"
        data = session.model_dump(mode="json")
        self._write_json(path, data)
        return path

    def load(self, session_id: str) -> Session:
        """Load a session by ID. Raises FileNotFoundError if missing."""
        path = self._session_dir(session_id) / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")
        data = self._read_json(path)
        return Session(**data)

    def exists(self, session_id: str) -> bool:
        return (self._session_dir(session_id) / "session.json").exists()

    def delete(self, session_id: str) -> None:
        """Remove all data for a session."""
        import shutil

        session_dir = self._session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        **extra_fields: Any,
    ) -> Session:
        """Atomically update session status and optional extra fields."""
        session = self.load(session_id)
        session = session.model_copy(
            update={"status": status, **extra_fields}
        )
        self.save(session)
        return session

    def list_sessions(
        self,
        status: SessionStatus | None = None,
        target: str | None = None,
    ) -> list[Session]:
        """List all sessions, optionally filtered by status or target."""
        sessions: list[Session] = []
        if not self._base_dir.exists():
            return sessions

        for child in sorted(self._base_dir.iterdir()):
            meta_file = child / "session.json"
            if child.is_dir() and meta_file.exists():
                try:
                    s = Session(**self._read_json(meta_file))
                    if status and s.status != status:
                        continue
                    if target and s.target.value != target:
                        continue
                    sessions.append(s)
                except Exception as exc:
                    logger.debug("Skipping corrupt session %s: %s", child.name, exc)
        return sessions

    def session_dir(self, session_id: str) -> Path:
        """Public accessor for a session's directory."""
        return self._session_dir(session_id)

    def results_dir(self, session_id: str) -> Path:
        d = self._session_dir(session_id) / "results"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clean(
        self,
        older_than_seconds: int | None = None,
        statuses: list[SessionStatus] | None = None,
    ) -> int:
        """Remove sessions matching criteria. Returns count deleted."""
        now = datetime.now(UTC)
        removed = 0
        for session in self.list_sessions():
            if statuses and session.status not in statuses:
                continue
            if older_than_seconds:
                age = (now - session.started_at).total_seconds()
                if age < older_than_seconds:
                    continue
            self.delete(session.id)
            removed += 1
        return removed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        return self._base_dir / session_id

    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON with file-locking for atomicity."""
        with open(path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _read_json(self, path: Path) -> dict:
        with open(path) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
