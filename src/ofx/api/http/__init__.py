"""HTTP client with connection pooling and retry logic.

Optimized for red teaming operations with:
- Connection pooling for better performance
- Automatic retries with exponential backoff
- Rate limiting support
- Custom headers and timeouts
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

import httpx

from ofx.api._compat import APIError, OFXTimeoutError

_http_client: httpx.Client | None = None
_T = TypeVar("_T")


def get_http_client(
    timeout: int = 30,
    max_connections: int = 100,
    max_keepalive_connections: int = 20,
) -> httpx.Client:
    """Get or create a reusable HTTP client with connection pooling."""
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
        )
        _http_client = httpx.Client(
            timeout=timeout,
            limits=limits,
            follow_redirects=True,
        )
    return _http_client


def close_http_clients() -> None:
    """Close all HTTP clients and free resources."""
    global _http_client
    if _http_client:
        _http_client.close()
        _http_client = None


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, calls_per_second: float = 10.0) -> None:
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0

    def wait(self) -> None:
        """Wait if necessary to respect rate limit."""
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


@lru_cache(maxsize=10)
def get_rate_limiter(calls_per_second: float = 10.0) -> RateLimiter:
    """Get a cached rate limiter instance."""
    return RateLimiter(calls_per_second)


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (
        httpx.RequestError,
        httpx.HTTPStatusError,
    ),
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Decorator for retrying functions with exponential backoff."""
    def decorator(func: Callable[..., _T]) -> Callable[..., _T]:
        def wrapper(*args: object, **kwargs: object) -> _T:
            last_exception: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:  # type: ignore[misc]
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = backoff_factor ** attempt
                        time.sleep(wait_time)
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry wrapper failed without exception")
        return wrapper
    return decorator


def fetch(
    url: str,
    max_retries: int = 3,
    timeout: int = 30,
    rate_limit: float | None = None,
    **kwargs: Any,
) -> str:
    """Send a GET request with retry logic and connection pooling.

    Args:
        url: The URL to fetch
        max_retries: Number of retry attempts on failure
        timeout: Request timeout in seconds
        rate_limit: Rate limit in calls per second (optional)
        **kwargs: Additional arguments passed to httpx.get()

    Returns:
        Response text

    Raises:
        APIError: If request fails after retries
        OFXTimeoutError: If request times out
    """
    client = get_http_client(timeout=timeout)

    if rate_limit:
        limiter = get_rate_limiter(rate_limit)
        limiter.wait()

    @retry_with_backoff(max_retries=max_retries)
    def _fetch() -> str:
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as e:
            raise OFXTimeoutError(f"Request to {url} timed out", timeout_seconds=timeout) from e
        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code} error for {url}",
                status_code=e.response.status_code,
                response=e.response.text
            ) from e
        except httpx.RequestError as e:
            raise APIError(f"Request failed: {str(e)}") from e

    return _fetch()


def post(
    url: str,
    data: dict[str, Any] | str,
    max_retries: int = 3,
    timeout: int = 30,
    rate_limit: float | None = None,
    **kwargs: Any,
) -> str:
    """Send a POST request with retry logic and connection pooling."""
    client = get_http_client(timeout=timeout)

    if rate_limit:
        limiter = get_rate_limiter(rate_limit)
        limiter.wait()

    @retry_with_backoff(max_retries=max_retries)
    def _post() -> str:
        try:
            response = client.post(
                url,
                json=data if isinstance(data, dict) else None,
                data=data if isinstance(data, str) else None,
                **kwargs
            )
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as e:
            raise OFXTimeoutError(f"Request to {url} timed out", timeout_seconds=timeout) from e
        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code} error for {url}",
                status_code=e.response.status_code,
                response=e.response.text
            ) from e
        except httpx.RequestError as e:
            raise APIError(f"Request failed: {str(e)}") from e

    return _post()


requests = httpx


__all__ = [
    "fetch",
    "post",
    "requests",
    "get_http_client",
    "close_http_clients",
    "RateLimiter",
    "retry_with_backoff",
]
