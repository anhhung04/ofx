"""Core abstractions for the OFX API package.

Provides:
- `Result` type for functional error handling.
- `BaseRunner` protocol for post‑execution runners.
- `SearchClient` abstract base class for external search services.
- `WebShellGenerator` protocol for language‑specific web‑shell generators.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


class Result[T]:
    """Simple Result/Either type.

    ``Result`` instances are either ``Ok(value)`` or ``Err(error)``.
    ``is_ok``/``is_err`` helpers allow explicit checking.
    """

    __slots__ = ("_value", "_error", "_ok")

    def __init__(
        self, value: T | None = None, error: Exception | None = None, ok: bool = True
    ):
        self._value = value
        self._error = error
        self._ok = ok

    @classmethod
    def Ok(cls, value: T) -> Result[T]:
        return cls(value=value, ok=True)

    @classmethod
    def Err(cls, error: Exception) -> Result[Any]:
        return cls(error=error, ok=False)

    def is_ok(self) -> bool:
        return self._ok

    def is_err(self) -> bool:
        return not self._ok

    def unwrap(self) -> T:
        if self._ok:
            return self._value  # type: ignore[return-value]
        raise self._error or RuntimeError("Result has no error")

    def unwrap_err(self) -> Exception:
        if not self._ok:
            return self._error or RuntimeError("Result has no error")
        raise ValueError("Result is Ok, no error present")

    def map(self, fn: Callable[[T], Any]) -> Result[Any]:
        if self._ok:
            try:
                return Result.Ok(fn(self._value))  # type: ignore[arg-type]
            except Exception as exc:  # pragma: no cover
                return Result.Err(exc)
        return Result.Err(self._error or RuntimeError("Unknown error"))

    def __repr__(self) -> str:
        if self._ok:
            return f"Ok({self._value!r})"
        return f"Err({self._error!r})"


@runtime_checkable
class BaseRunner(Protocol):
    """Protocol for post‑execution runners (SSH, WinRM, etc.)."""

    def run(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class SearchClient(Protocol):
    """Base class for external search services.

    Sub‑classes must implement ``search`` returning a ``Result`` with a list of
    dictionaries representing raw results.
    """

    async def search(
        self, query: str, **kwargs: Any
    ) -> Result[list[dict[str, Any]]]: ...


@runtime_checkable
class WebShellGenerator(Protocol):
    """Web shell generator protocol."""

    """Protocol for language‑specific web‑shell generators.

    ``generate`` receives a payload string and optional keyword arguments and
    returns the rendered web‑shell source.
    """

    def generate(self, payload: str, **kwargs: Any) -> str: ...
