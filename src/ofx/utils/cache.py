"""Caching utilities for performance optimization."""

from collections.abc import Callable
from functools import lru_cache, wraps
from typing import Any, TypeVar

T = TypeVar("T")


def async_lru_cache(maxsize: int = 128):
    """LRU cache decorator for async functions."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict[Any, T] = {}
        cache_order: list[Any] = []

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            key = (args, tuple(sorted(kwargs.items())))

            if key in cache:
                cache_order.remove(key)
                cache_order.append(key)
                return cache[key]

            result = await func(*args, **kwargs)

            cache[key] = result
            cache_order.append(key)

            if len(cache) > maxsize:
                oldest = cache_order.pop(0)
                del cache[oldest]

            return result

        def cache_clear() -> None:
            cache.clear()
            cache_order.clear()

        def cache_info() -> dict[str, Any]:
            return {"hits": 0, "misses": 0, "maxsize": maxsize, "currsize": len(cache)}

        wrapper.cache_clear = cache_clear
        wrapper.cache_info = cache_info

        return wrapper

    return decorator


@lru_cache(maxsize=256)
def cached_path_resolve(path_str: str) -> str:
    """Cache Path resolution to avoid repeated filesystem operations."""
    from pathlib import Path

    return str(Path(path_str).resolve())


@lru_cache(maxsize=64)
def cached_which(command: str) -> str:
    """Cache shutil.which results."""
    import shutil

    result = shutil.which(command)
    return result or ""
