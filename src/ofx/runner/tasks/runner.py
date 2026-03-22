"""TaskRunner — executes a registered task and stores typed outputs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.command import Command
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys
from ofx.tasks.base import Task
from ofx.tasks.output_types import OutputType
from ofx.tasks.registry import TaskRegistry


class TaskExecution(BaseModel):
    """Model describing a single task execution."""

    task_name: str = Field(..., description="Registered task name")
    target: str = Field(default="", description="Primary target for the task")
    opts: dict[str, Any] = Field(
        default_factory=dict, description="Task-specific options"
    )
    shell: str = Field(default="/bin/bash", description="Shell to use")
    working_directory: Path = Field(
        default_factory=Path.cwd, description="Working directory"
    )
    timeout_minutes: int = Field(default=60 * 24, description="Timeout in minutes")

    def __str__(self) -> str:
        return f"TaskExecution(task='{self.task_name}', target='{self.target}')"


class TaskRunner(BaseRunner[TaskExecution]):
    """Runner that wraps a :class:`Task` tool definition.

    Lifecycle:
      1. ``_pre_run``  — resolve task from registry, validate it exists
      2. ``_do_run``   — build command, execute, parse output, store typed results
      3. ``_post_run`` — no-op (results already stored)
    """

    def __init__(
        self,
        model: TaskExecution,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        logger: logging.Logger | None = None,
    ):
        super().__init__(model, ctx, parent, None, logger=logger)
        self._task: Task | None = None
        self._output_file: Path | None = None

    def _produce_log(self, message: str) -> str:
        return f"[Task:{self.model.task_name}] {message}"

    # ── Lifecycle ──────────────────────────────────────────────────

    async def _pre_run(self) -> None:
        task_cls = TaskRegistry.get(self.model.task_name)
        if task_cls is None:
            available = ", ".join(TaskRegistry.list_tasks()) or "(none)"
            raise RuntimeError(
                f"Task '{self.model.task_name}' is not registered. "
                f"Available tasks: {available}"
            )
        self._task = task_cls()

    async def _do_run(self) -> None:
        assert self._task is not None

        outputs: dict[str, Any] = {}
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)

        # Build command
        cmd_str, self._output_file = self._task.build_command(
            self.model.target, **self.model.opts
        )
        self._log_info(f"Command: {cmd_str}")

        # Execute via shared CommandExecutor
        cmd_model = Command(
            cmd=cmd_str,
            shell=self.model.shell,
            working_directory=self.model.working_directory,
            timeout_minutes=self.model.timeout_minutes,
        )
        executor = CommandExecutor(cmd_model, self.ctx.envs)
        executor.prepare_outputs_file()
        result: CommandExecutionResult | None = None

        try:
            result = await executor.execute()
            executor.raise_for_status(result.exit_code, result.stderr)
        except TimeoutError:
            raise RuntimeError(
                f"Task '{self.model.task_name}' timed out after "
                f"{self.model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Task '{self.model.task_name}' error: {e}") from e
        finally:
            if result is None:
                result = CommandExecutionResult(
                    exit_code=None, stdout="", stderr="", outputs={}
                )

            # Parse structured output
            typed_outputs = self._parse_outputs(result)

            # Store regular outputs
            outputs.update(
                {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "typed_outputs": [o.to_dict() for o in typed_outputs],
                }
            )
            outputs.update(result.outputs)
            await self.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)

            # Capture $RUNNER_OUTPUTS file contents
            await executor.capture_outputs_file(
                self,
                RunnerRegistryKeys.OUTPUTS,
                lambda msg: self._log_debug(msg),
            )

            # Clean up temp output file
            self._cleanup_output_file()

    async def _post_run(self) -> None:
        pass

    # ── Helpers ────────────────────────────────────────────────────

    def _parse_outputs(self, result: CommandExecutionResult) -> list[OutputType]:
        """Delegate to the task's parse_output method with deduplication."""
        assert self._task is not None
        try:
            raw = self._task.parse_output(
                stdout=result.stdout,
                stderr=result.stderr,
                output_file=self._output_file,
            )
            return self._deduplicate(raw)
        except Exception as e:
            self._log_warning(f"Output parsing failed: {e}")
            return []

    @staticmethod
    def _deduplicate(items: list[OutputType]) -> list[OutputType]:
        """Remove duplicates using each item's ``_uuid`` hash."""
        seen: set[str] = set()
        unique: list[OutputType] = []
        for item in items:
            uid = item._uuid
            if uid not in seen:
                seen.add(uid)
                unique.append(item)
        return unique

    def _cleanup_output_file(self) -> None:
        if self._output_file and self._output_file.exists():
            try:
                self._output_file.unlink()
            except OSError:
                pass
