"""Core abstractions for the OFX API package."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PostRunnerProtocol(Protocol):
    """Protocol for post-execution runners (SSH, WinRM, etc.)."""

    def run(self, *args: Any, **kwargs: Any) -> Any: ...
