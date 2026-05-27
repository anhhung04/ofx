"""Structured lifecycle event emission for runners."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ofx.runner.core.base import BaseRunner


class EventEmitter:
    """Best-effort NDJSON event emitter for runner lifecycle events."""

    __slots__ = ("_runner", "_listeners")

    def __init__(self, runner: BaseRunner[Any]) -> None:
        self._runner = runner
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def add_event_listener(
        self, event_type: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register an in-process event listener."""
        self._listeners.setdefault(event_type, []).append(callback)

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit a structured runner lifecycle event as NDJSON and callbacks."""
        entry = self._build_entry(event_type, payload)
        self._emit_to_sink(entry)
        self._emit_to_listeners(event_type, entry)

    def _build_entry(
        self, event_type: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "runner_type": self._runner.__class__.__name__,
            "run_id": self._runner.run_id,
            "status": self._runner.status.value,
            "name": getattr(self._runner.model, "name", ""),
            "job_id": getattr(self._runner.model, "jid", None),
            "step_index": getattr(self._runner.model, "step_index", None),
            "parent_run_id": self._runner.parent.run_id if self._runner.parent else None,
        }
        if payload:
            entry.update(payload)
        return entry

    def _emit_to_sink(self, entry: dict[str, Any]) -> None:
        sink = self._event_sink_path()
        if sink is None:
            return
        try:
            sink.parent.mkdir(parents=True, exist_ok=True)
            with open(sink, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as exc:
            self._runner._log_warning(f"event emit failed: {exc}")

    def _emit_to_listeners(self, event_type: str, entry: dict[str, Any]) -> None:
        for callback in self._listeners.get(event_type, []):
            try:
                callback(entry)
            except Exception as exc:
                self._runner._log_warning(f"event listener failed: {exc}")

    def _event_sink_path(self) -> Path | None:
        path = getattr(self._runner.ctx, "event_sink_path", None)
        if path:
            return path
        return None
