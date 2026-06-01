from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from ofx.runner import RunContext, RunnerStatus
from ofx.runner.logging import LogContext, ModelContext
from ofx.runner.services.event_emitter import EventEmitter


class _Runner:
    def __init__(self, *, event_sink_path=None):
        self.run_id = "run-1"
        self.status = RunnerStatus.COMPLETED
        self.model = SimpleNamespace(name="job-name", jid="job-1", step_index=2)
        self.parent = SimpleNamespace(run_id="parent-1")
        self.ctx = RunContext(event_sink_path=event_sink_path)
        self.warnings: list[str] = []

    def _log_warning(self, message: str) -> None:
        self.warnings.append(message)


def test_build_entry_uses_log_context_metadata():
    runner = _Runner()
    emitter = EventEmitter(runner)
    received = []
    emitter.add_event_listener("runner_finish", lambda entry: received.append(entry))

    emitter.emit("runner_finish", {"extra": "value"})
    entry = received[0]

    assert entry["event_type"] == "runner_finish"
    assert entry["runner_type"] == "_Runner"
    assert entry["run_id"] == "run-1"
    assert entry["status"] == "completed"
    assert entry["name"] == "job-name"
    assert entry["job_id"] == "job-1"
    assert entry["step_index"] == 2
    assert entry["parent_run_id"] == "parent-1"
    assert entry["extra"] == "value"


def test_build_entry_derives_log_context_once():
    runner = _Runner()
    emitter = EventEmitter(runner)
    received = []
    emitter.add_event_listener("runner_finish", lambda entry: received.append(entry))
    context = LogContext(
        run_id="run-1",
        runner_type="_Runner",
        model_name="job-name",
        model_jid="job-1",
        step_index=2,
        status="completed",
        parent_run_id="parent-1",
    )

    with patch(
        "ofx.runner.services.event_emitter.LogContext.from_runner",
        return_value=context,
    ) as mock_from_runner:
        emitter.emit("runner_finish")
        entry = received[0]

    mock_from_runner.assert_called_once_with(runner)
    assert entry["runner_type"] == "_Runner"
    assert entry["run_id"] == "run-1"


def test_model_context_and_log_context_extract_runner_metadata():
    runner = _Runner()
    runner.status = RunnerStatus.FINISHED

    model_context = ModelContext.from_model(runner.model)
    log_context = LogContext.from_runner(runner)

    assert model_context.name == "job-name"
    assert model_context.jid == "job-1"
    assert model_context.step_index == 2
    assert log_context.model_name == "job-name"
    assert log_context.model_jid == "job-1"
    assert log_context.step_index == 2
    assert log_context.status == "completed"


def test_emit_writes_to_sink_and_notifies_listeners(tmp_path):
    sink = tmp_path / "events.ndjson"
    runner = _Runner(event_sink_path=sink)
    emitter = EventEmitter(runner)
    received = []
    emitter.add_event_listener("runner_start", lambda entry: received.append(entry))

    emitter.emit("runner_start", {"phase": 1})

    lines = sink.read_text().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["event_type"] == "runner_start"
    assert stored["phase"] == 1
    assert received == [stored]


def test_emit_warns_when_listener_raises():
    runner = _Runner()
    emitter = EventEmitter(runner)
    emitter.add_event_listener("runner_start", lambda _entry: (_ for _ in ()).throw(RuntimeError("boom")))

    emitter.emit("runner_start")

    assert runner.warnings == ["event listener failed: boom"]
