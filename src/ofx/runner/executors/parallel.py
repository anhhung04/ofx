"""Shared bounded parallel execution helpers for runner executors."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from ofx.runner.context import RunnerStatus, RunResult

T = TypeVar("T")
R = TypeVar("R")

async def run_limited_fail_fast(
    items: Sequence[T],
    *,
    max_parallel: int,
    fail_fast: bool,
    run_item: Callable[[int, T], Awaitable[R]],
    is_failure: Callable[[R], bool],
) -> list[R | Exception | None]:
    """Run indexed items with bounded concurrency and cooperative fail-fast."""
    semaphore = asyncio.Semaphore(max_parallel)
    failed_event = asyncio.Event()

    async def run_instance(index: int, item: T) -> R | None:
        if fail_fast and failed_event.is_set():
            return None

        async with semaphore:
            if fail_fast and failed_event.is_set():
                return None
            try:
                result = await run_item(index, item)
            except Exception:
                if fail_fast:
                    failed_event.set()
                raise

            if fail_fast and is_failure(result):
                failed_event.set()
            return result

    tasks = [
        asyncio.create_task(run_instance(index, item))
        for index, item in enumerate(items)
    ]
    return await asyncio.gather(*tasks, return_exceptions=True)

async def run_parallel_runner_items[TItem](
    items: Sequence[TItem],
    *,
    max_parallel: int,
    fail_fast: bool,
    run_item: Callable[[int, TItem], Awaitable[RunResult]],
    describe_item: Callable[[int, TItem], str],
) -> list[str]:
    """Run runner-producing items in parallel and collect any errors."""
    results = await run_limited_fail_fast(
        items,
        max_parallel=max_parallel,
        fail_fast=fail_fast,
        run_item=run_item,
        is_failure=lambda result: result.status != RunnerStatus.COMPLETED,
    )
    return collect_parallel_run_errors(
        items,
        results,
        describe_item=describe_item,
    )

def parallel_run_settings(strategy, *, item_count: int) -> tuple[int, bool]:
    """Derive bounded-parallel settings from an optional strategy object."""
    if strategy is None:
        return item_count, True
    return strategy.max_parallel, strategy.fail_fast

def collect_parallel_run_errors[TItem](
    items: Sequence[TItem],
    results: Sequence[RunResult | Exception | None],
    *,
    describe_item: Callable[[int, TItem], str],
) -> list[str]:
    """Collect error strings from bounded-parallel runner results."""
    errors: list[str] = []
    for index, result in enumerate(results):
        if result is None:
            continue

        item = items[index]
        prefix = describe_item(index, item)
        if isinstance(result, Exception):
            errors.append(f"{prefix}: {result}")
        elif result.status != RunnerStatus.COMPLETED:
            errors.append(f"{prefix}: {result.error or 'Failed'}")
    return errors

__all__ = [
    "collect_parallel_run_errors",
    "parallel_run_settings",
    "run_limited_fail_fast",
    "run_parallel_runner_items",
]
