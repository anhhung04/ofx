"""Regression tests for the async-safe timeline source-host lookup.

Covers finding L15: ``timeline._source_host()`` performs blocking urllib
calls (up to 3 services, 2s each) on first use; that lookup must not run on
the event loop inside ``StepExecutor.post_run``. ``_source_host_async`` and
``log_step_async`` offload the blocking lookup to a worker thread while
keeping the module-global cache and the per-service 2s timeout.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from ofx.runner import timeline


def _clear_cache(monkeypatch) -> None:
    monkeypatch.setattr(timeline, "_source_host_cache", "")


def test_source_host_async_returns_cached_value_without_network(monkeypatch):
    """A warm cache must be returned without touching a thread or network."""
    _clear_cache(monkeypatch)
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_HOST", "myhost")
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_IP", "1.2.3.4")
    expected = timeline._source_host()  # fast path: env vars, no network

    with patch("ofx.runner.timeline.asyncio.to_thread") as mock_to_thread:
        result = asyncio.run(timeline._source_host_async())

    assert result == expected == "myhost (1.2.3.4)"
    mock_to_thread.assert_not_called()


def test_source_host_async_offloads_uncached_lookup_to_thread(monkeypatch):
    """A cold cache must run the blocking lookup via asyncio.to_thread."""
    _clear_cache(monkeypatch)

    with patch(
        "ofx.runner.timeline.asyncio.to_thread",
        new=AsyncMock(return_value="thread-host (9.9.9.9)"),
    ) as mock_to_thread:
        result = asyncio.run(timeline._source_host_async())

    assert result == "thread-host (9.9.9.9)"
    mock_to_thread.assert_awaited_once_with(timeline._source_host)


def test_source_host_async_populates_shared_cache(monkeypatch):
    """The async lookup fills the same module-global cache as the sync one."""
    _clear_cache(monkeypatch)
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_HOST", "host-a")
    monkeypatch.setenv("OFX_COMMAND_LOG_SOURCE_IP", "5.6.7.8")

    asyncio.run(timeline._source_host_async())
    assert timeline._source_host_cache == "host-a (5.6.7.8)"
    assert timeline._source_host() == "host-a (5.6.7.8)"


def test_log_step_async_writes_same_ndjson_format(tmp_path, monkeypatch):
    """log_step_async produces the same record as log_step for a given host."""
    from ofx.runner.timeline import log_step, log_step_async

    monkeypatch.delenv("OFX_COMMAND_LOG_FILE", raising=False)
    sync_path = tmp_path / "sync.ndjson"
    async_path = tmp_path / "async.ndjson"
    monkeypatch.setenv("OFX_COMMAND_LOG_FILE", str(sync_path))

    common = {
        "ctx_vars": {"project_name": "proj"},
        "step_name": "scan",
        "command": "nmap -sV 10.0.0.1",
        "tool": "nmap",
        "target": "10.0.0.1",
        "status": "completed",
        "duration_ms": 1200,
        "exit_code": 0,
        "source_host": "host (1.2.3.4)",
    }
    log_step(**common)

    monkeypatch.setenv("OFX_COMMAND_LOG_FILE", str(async_path))
    asyncio.run(log_step_async(**common))

    sync_record = json.loads(sync_path.read_text().splitlines()[0])
    async_record = json.loads(async_path.read_text().splitlines()[0])
    assert sync_record == async_record
    assert async_record["source_host"] == "host (1.2.3.4)"
