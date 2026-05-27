from abc import ABC, abstractmethod


class Executor(ABC):
    """Pluggable execution strategy for a Runner."""

    @abstractmethod
    async def pre_run(self, runner) -> None:
        """Prepare for execution."""

    @abstractmethod
    async def do_run(self, runner) -> None:
        """Execute the main logic."""

    @abstractmethod
    async def post_run(self, runner) -> None:
        """Clean up after execution."""

    async def on_failure(self, runner) -> None:
        """Cleanup when execution fails. Default no-op."""
        return None


from ofx.runner.executors.cloud import CloudExecutor  # noqa: E402,F401
from ofx.runner.executors.fleet import FleetExecutor  # noqa: E402,F401
from ofx.runner.executors.job import JobExecutor, MatrixExecutor  # noqa: E402,F401
from ofx.runner.executors.step import StepExecutor  # noqa: E402,F401
from ofx.runner.executors.workflow import WorkflowExecutor  # noqa: E402,F401
def __getattr__(name: str):
    if name == "PipeExecutor":
        from ofx.runner.execution.pipe import PipeRunner

        return PipeRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
