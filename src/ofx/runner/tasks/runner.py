"""TaskRunner — executes a registered task and stores typed outputs."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.runner.commands.command_executor import CommandExecutionResult
from ofx.runner.context import RunContext
from ofx.runner.executors.task import TaskExecutor
from ofx.runner.runner import Runner
from ofx.runner.target_paths import sanitize_target_slug
from ofx.settings import DEFAULT_SHELL
from ofx.tasks.base import Task
from ofx.tasks.output_types import OutputType

logger = logging.getLogger(__name__)

class TaskExecution(BaseModel):
    """Model describing a single task execution."""

    task_name: str = Field(..., description="Registered task name")
    target: str = Field(default="", description="Primary target for the task")
    opts: dict[str, Any] = Field(
        default_factory=dict, description="Task-specific options"
    )
    shell: str = Field(default=DEFAULT_SHELL, description="Shell to use")
    working_directory: Path = Field(
        default_factory=Path.cwd, description="Working directory"
    )
    timeout_minutes: int = Field(default=60 * 24, description="Timeout in minutes")
    store_creds: bool = Field(
        default=False,
        description="Store discovered UserAccount credentials into the credential store",
    )

class TaskRunner(Runner[TaskExecution]):
    """Runner that wraps a :class:`Task` tool definition.

    The execution lifecycle is delegated to :class:`TaskExecutor`; this class
    keeps task-specific parsing, streaming, profile, and export helpers close
    to the task state they operate on.

    Live Streaming:
      When ``stream=True`` (default), uses line-by-line stdout reading and
      parses items as they arrive, publishing each to the ``task:<name>:items``
      channel for real-time consumption.
    """

    def __init__(
        self,
        model: TaskExecution,
        ctx: RunContext,
        parent: Runner | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(
            model,
            ctx,
            parent,
            None,
            executor=TaskExecutor(),
            logger=logger,
        )
        self._task: Task | None = None
        self._output_file: Path | None = None
        self._streamed_items: list[OutputType] = []

    def _produce_log(self, message: str) -> str:
        return f"[Task:{self.model.task_name}] {message}"

    def _apply_profile_task_options(self) -> None:
        """Merge profile settings into the execution opts.

        Two layers of injection (both use user opts as highest priority):

        1. **Common metadata** — profile-level ``proxy``, ``threads``,
           ``rate_limit``, ``delay``, and ``user_agent`` are auto-mapped to
           matching task opt names when the task declares a compatible opt.
        2. **Per-task overrides** — ``profile.task_options[task_name]`` dict
           provides task-specific defaults.
        """
        profile = self.ctx.vars.get("profile_model")
        if not profile:
            return

        from ofx.runner.task_profile_options import merge_profile_task_options

        merged_opts, injected, override_keys = merge_profile_task_options(
            task_name=self.model.task_name,
            user_opts=self.model.opts,
            task_declared_opts=self._task.opts if self._task is not None else {},
            profile=profile,
        )
        self.model.opts = merged_opts
        if injected:
            self._log_debug(f"Injected profile common opts: {', '.join(injected)}")
        if override_keys:
            self._log_debug(
                f"Applied profile task_options for '{self.model.task_name}': "
                f"{override_keys}"
            )

    def _on_stdout_line(self, line: str) -> None:
        """Called for each stdout line during streaming execution.

        Attempts to parse the line into typed output items and publishes
        them to the channel store for real-time consumption.
        """
        try:
            assert self._task is not None
            items = self._task.parse_line(line)
        except Exception as e:
            logger.debug("Non-parseable line (task=%s): %s", self.model.task_name, e)
            return

        if not items:
            return

        new_items = self._deduplicate_with_seen(
            items,
            {item._uuid for item in self._streamed_items},
        )
        self._streamed_items.extend(new_items)
        if not new_items:
            return

        try:
            from ofx.runner.channels import get_channel_store

            store = get_channel_store()
            channel = f"task:{self.model.task_name}:items"
            for item in new_items:
                store.publish(channel, item.to_dict())
        except Exception as e:
            logger.debug(
                "Channel publish failed (task=%s): %s", self.model.task_name, e
            )

    def _parse_outputs(self, result: CommandExecutionResult) -> list[OutputType]:
        """Delegate to the task's parse_output method with deduplication.

        If streaming was active, merges streamed items with any additional
        items discovered from the output file.
        """
        try:
            assert self._task is not None
            parsed_output_items = self._task.parse_output(
                stdout=result.stdout,
                stderr=result.stderr,
                output_file=self._output_file,
            )
            return self._deduplicate_with_seen(
                self._streamed_items + list(parsed_output_items),
                set(),
            )
        except Exception as e:
            self._log_warning(f"Output parsing failed: {e}")
            return list(self._streamed_items)

    @staticmethod
    def _deduplicate_with_seen(
        items: Sequence[OutputType],
        seen: set[str],
    ) -> list[OutputType]:
        """Deduplicate items while extending an existing UUID set."""
        unique: list[OutputType] = []
        for item in items:
            uid = item._uuid
            if uid not in seen:
                seen.add(uid)
                unique.append(item)
        return unique

    def _export_output_file(self) -> Path | None:
        """Copy task output file to output_path with target in the filename.

        Creates ``<output_path>/scans/<task>_<target>.<ext>`` so results are
        organized by tool and target.  Returns the exported path, or None
        if there is nothing to export.
        """
        if not self._output_file or not self._output_file.exists():
            return None
        if not self.ctx.output_path:
            return None
        try:
            if self._output_file.stat().st_size == 0:
                return None
        except OSError:
            return None

        task_name = self.model.task_name
        target_slug = sanitize_target_slug(self.model.target)
        suffix = self._output_file.suffix or ".txt"
        filename = (
            f"{task_name}_{target_slug}{suffix}" if target_slug else f"{task_name}{suffix}"
        )
        dest = self.ctx.output_path / "scans" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(self._output_file), str(dest))
            self._log_debug(f"Exported output to {dest}")
            return dest
        except OSError as e:
            self._log_debug(f"Failed to export output file: {e}")
            return None
