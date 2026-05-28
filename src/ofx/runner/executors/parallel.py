"""Shared bounded parallel execution helpers for runner executors."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

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


__all__ = ["run_limited_fail_fast"]
