"""Tests for shared executor parallel orchestration helpers."""

from __future__ import annotations

import asyncio

import pytest

from ofx.runner.executors.parallel import run_limited_fail_fast


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
