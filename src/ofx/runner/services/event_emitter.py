"""Structured lifecycle event emission for runners."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ofx.runner.logging import LogContext

if TYPE_CHECKING:
    from ofx.runner.runner import Runner

class EventEmitter:
    """Best-effort NDJSON event emitter for runner lifecycle events."""

    __slots__ = ("_runner", "_listeners", "_sink_handle", "_sink_path")

    def __init__(self, runner: Runner[Any]) -> None:
        self._runner = runner
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._sink_handle: Any = None
        self._sink_path: Path | None = None

    def add_event_listener(
        self, event_type: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register an in-process event listener."""
        self._listeners.setdefault(event_type, []).append(callback)

    def _close_sink(self) -> None:
        """Close the lazily-opened NDJSON sink handle, if any."""
        if self._sink_handle is not None:
            try:
                self._sink_handle.close()
            except Exception:
                pass
            self._sink_handle = None
            self._sink_path = None

    def close(self) -> None:
        """Close the NDJSON sink handle, if one was opened."""
        self._close_sink()

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit a structured runner lifecycle event as NDJSON and callbacks."""
        context = LogContext.from_runner(self._runner)
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "runner_type": context.runner_type,
            "run_id": context.run_id,
            "status": context.status,
            "name": context.model_name or "",
            "job_id": context.model_jid,
            "step_index": context.step_index,
            "parent_run_id": context.parent_run_id,
        }
        if payload:
            entry.update(payload)

        sink = self._runner.ctx.event_sink_path or None
        if sink is not None:
            try:
                if self._sink_handle is None or self._sink_path != sink:
                    self._close_sink()
                    sink.parent.mkdir(parents=True, exist_ok=True)
                    self._sink_handle = open(sink, "a", encoding="utf-8")
                    self._sink_path = sink
                self._sink_handle.write(json.dumps(entry, default=str) + "\n")
                self._sink_handle.flush()
            except Exception as exc:
                self._close_sink()
                self._runner._log_warning(f"event emit failed: {exc}")

        for callback in tuple(self._listeners.get(event_type, ())):
            try:
                callback(entry)
            except Exception as exc:
                self._runner._log_warning(f"event listener failed: {exc}")
