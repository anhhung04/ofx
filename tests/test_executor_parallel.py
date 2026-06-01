"""Tests for shared executor parallel orchestration helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ofx.runner import RunResult, RunnerStatus
from ofx.runner.executors.parallel import (
    collect_parallel_run_errors,
    parallel_run_settings,
    run_limited_fail_fast,
    run_parallel_runner_items,
)


@pytest.mark.asyncio
async def test_run_limited_fail_fast_respects_max_parallel():
    active = 0
    max_seen = 0

    async def run_item(_index: int, value: int) -> int:
        nonlocal active, max_seen
        active += 1
        max_seen = max(max_seen, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    results = await run_limited_fail_fast(
        [1, 2, 3, 4],
        max_parallel=2,
        fail_fast=True,
        run_item=run_item,
        is_failure=lambda _result: False,
    )

    assert results == [1, 2, 3, 4]
    assert max_seen == 2


@pytest.mark.asyncio
async def test_run_limited_fail_fast_skips_queued_items_after_failure_result():
    calls: list[int] = []

    async def run_item(index: int, _value: str) -> str:
        calls.append(index)
        return "fail" if index == 0 else "ok"

    results = await run_limited_fail_fast(
        ["a", "b", "c"],
        max_parallel=1,
        fail_fast=True,
        run_item=run_item,
        is_failure=lambda result: result == "fail",
    )

    assert results == ["fail", None, None]
    assert calls == [0]


@pytest.mark.asyncio
async def test_run_limited_fail_fast_skips_queued_items_after_exception():
    async def run_item(index: int, _value: str) -> str:
        if index == 0:
            raise RuntimeError("boom")
        return "ok"

    results = await run_limited_fail_fast(
        ["a", "b"],
        max_parallel=1,
        fail_fast=True,
        run_item=run_item,
        is_failure=lambda _result: False,
    )

    assert isinstance(results[0], RuntimeError)
    assert results[1] is None


@pytest.mark.asyncio
async def test_run_limited_fail_fast_false_runs_remaining_items_after_exception():
    async def run_item(index: int, _value: str) -> str:
        if index == 0:
            raise RuntimeError("boom")
        return "ok"

    results = await run_limited_fail_fast(
        ["a", "b"],
        max_parallel=1,
        fail_fast=False,
        run_item=run_item,
        is_failure=lambda _result: False,
    )

    assert isinstance(results[0], RuntimeError)
    assert results[1] == "ok"


def test_collect_parallel_run_errors_includes_exception_and_failed_results():
    results = [
        RuntimeError("boom"),
        RunResult(name="job", run_id="2", status=RunnerStatus.FAILED, error="bad"),
        RunResult(name="job", run_id="3", status=RunnerStatus.COMPLETED),
        None,
    ]

    errors = collect_parallel_run_errors(
        ["a", "b", "c", "d"],
        results,
        describe_item=lambda idx, item: f"Item {idx} ({item})",
    )

    assert errors == [
        "Item 0 (a): boom",
        "Item 1 (b): bad",
    ]


def test_collect_parallel_run_errors_uses_default_failed_message():
    results = [
        RunResult(name="job", run_id="1", status=RunnerStatus.FAILED, error=None),
    ]

    errors = collect_parallel_run_errors(
        ["a"],
        results,
        describe_item=lambda idx, item: f"Item {idx} ({item})",
    )

    assert errors == ["Item 0 (a): Failed"]


@pytest.mark.asyncio
async def test_run_parallel_runner_items_collects_failed_results_and_exceptions():
    async def run_item(index: int, value: str) -> RunResult:
        if index == 0:
            return RunResult(name=value, run_id="1", status=RunnerStatus.FAILED, error="bad")
        if index == 1:
            raise RuntimeError("boom")
        return RunResult(name=value, run_id="3", status=RunnerStatus.COMPLETED)

    errors = await run_parallel_runner_items(
        ["a", "b", "c"],
        max_parallel=2,
        fail_fast=False,
        run_item=run_item,
        describe_item=lambda idx, item: f"Item {idx} ({item})",
    )

    assert errors == [
        "Item 0 (a): bad",
        "Item 1 (b): boom",
    ]


def test_parallel_run_settings_defaults_when_strategy_missing():
    assert parallel_run_settings(None, item_count=3) == (3, True)


def test_parallel_run_settings_uses_strategy_values():
    strategy = SimpleNamespace(max_parallel=2, fail_fast=False)
    assert parallel_run_settings(strategy, item_count=9) == (2, False)
