"""Caching utilities for performance optimization."""
from functools import lru_cache, wraps
from typing import Any, Callable, TypeVar
import asyncio

T = TypeVar('T')


def async_lru_cache(maxsize: int = 128):
    """LRU cache decorator for async functions."""
    def decorator(func: Callable) -> Callable:
        cache = {}
        cache_order = []
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a hashable key from args and kwargs
            key = (args, tuple(sorted(kwargs.items())))
            
            if key in cache:
                # Move to end (most recently used)
                cache_order.remove(key)
                cache_order.append(key)
                return cache[key]
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            cache[key] = result
            cache_order.append(key)
            
            # Evict oldest if cache is full
            if len(cache) > maxsize:
                oldest = cache_order.pop(0)
                del cache[oldest]
            
            return result
        
        wrapper.cache_clear = lambda: (cache.clear(), cache_order.clear())
        wrapper.cache_info = lambda: {
            'hits': 0,  # Could be tracked if needed
            'misses': 0,
            'maxsize': maxsize,
            'currsize': len(cache)
        }
        
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
