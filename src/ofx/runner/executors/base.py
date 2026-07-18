"""Base executor protocol for runner lifecycle hooks."""

from __future__ import annotations

from abc import ABC, abstractmethod

class Executor(ABC):
    """Pluggable execution strategy for a runner."""

    async def pre_run(self, runner) -> None:
        """Prepare the runner before main execution."""
        return None

    @abstractmethod
    async def do_run(self, runner) -> None:
        """Execute the runner's primary logic."""

    async def post_run(self, runner) -> None:
        """Finalize the runner after successful execution."""
        return None

    async def on_failure(self, runner) -> None:
        """Perform best-effort cleanup after a failed execution."""
        return None
