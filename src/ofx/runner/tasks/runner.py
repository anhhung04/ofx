"""TaskRunner — executes a registered task and stores typed outputs."""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.runner.commands.command_executor import CommandExecutionResult
from ofx.runner.context import RunContext
from ofx.runner.executors.task import TaskExecutor
from ofx.runner.logging import prefix_log
from ofx.runner.runner import BaseRunner
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

    def __str__(self) -> str:
        return f"TaskExecution(task='{self.task_name}', target='{self.target}')"


class TaskRunner(BaseRunner[TaskExecution]):
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
        parent: BaseRunner | None = None,
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
        return prefix_log(message, f"[Task:{self.model.task_name}]")

    # ── Profile integration ────────────────────────────────────────

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

        task_declared_opts = self._task.opts if self._task is not None else {}
        merged_opts, injected, override_keys = merge_profile_task_options(
            task_name=self.model.task_name,
            user_opts=self.model.opts,
            task_declared_opts=task_declared_opts,
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

    # ── Live streaming ─────────────────────────────────────────────

    def _on_stdout_line(self, line: str) -> None:
        """Called for each stdout line during streaming execution.

        Attempts to parse the line into typed output items and publishes
        them to the channel store for real-time consumption.
        """
        assert self._task is not None
        try:
            items = self._task.parse_line(line)
            if items:
                new_items = self._deduplicate_incremental(items)
                self._streamed_items.extend(new_items)
                if new_items:
                    self._publish_items(new_items)
        except Exception as e:
            logger.debug("Non-parseable line (task=%s): %s", self.model.task_name, e)

    def _publish_items(self, items: list[OutputType]) -> None:
        """Publish newly discovered items to the task channel."""
        try:
            from ofx.runner.channels import get_channel_store

            store = get_channel_store()
            channel = f"task:{self.model.task_name}:items"
            for item in items:
                store.publish(channel, item.to_dict())
        except Exception as e:
            logger.debug(
                "Channel publish failed (task=%s): %s", self.model.task_name, e
            )

    def _deduplicate_incremental(self, items: Sequence[OutputType]) -> list[OutputType]:
        """Deduplicate against already-streamed items."""
        return self._deduplicate_with_seen(
            items,
            {item._uuid for item in self._streamed_items},
        )

    # ── Helpers ────────────────────────────────────────────────────

    def _parse_outputs(self, result: CommandExecutionResult) -> list[OutputType]:
        """Delegate to the task's parse_output method with deduplication.

        If streaming was active, merges streamed items with any additional
        items discovered from the output file.
        """
        assert self._task is not None
        try:
            raw = self._task.parse_output(
                stdout=result.stdout,
                stderr=result.stderr,
                output_file=self._output_file,
            )
            all_items = list(self._streamed_items) + list(raw)
            return self._deduplicate(all_items)
        except Exception as e:
            self._log_warning(f"Output parsing failed: {e}")
            return list(self._streamed_items) if self._streamed_items else []

    @staticmethod
    def _deduplicate(items: list[OutputType]) -> list[OutputType]:
        """Remove duplicates using each item's ``_uuid`` hash."""
        return TaskRunner._deduplicate_with_seen(items, set())

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

    def _cleanup_output_file(self) -> None:
        if self._output_file and self._output_file.exists():
            try:
                self._output_file.unlink()
            except OSError as e:
                logger.debug(
                    "Failed to remove task output file %s: %s", self._output_file, e
                )

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
        # Skip empty output files
        try:
            if self._output_file.stat().st_size == 0:
                return None
        except OSError:
            return None

        task_name = self.model.task_name
        target_slug = self._sanitize_target(self.model.target)
        suffix = self._output_file.suffix or ".txt"

        if target_slug:
            filename = f"{task_name}_{target_slug}{suffix}"
        else:
            filename = f"{task_name}{suffix}"

        scans_dir = self.ctx.output_path / "scans"
        scans_dir.mkdir(parents=True, exist_ok=True)
        dest = scans_dir / filename

        try:
            shutil.copy2(str(self._output_file), str(dest))
            self._log_debug(f"Exported output to {dest}")
            return dest
        except OSError as e:
            self._log_debug(f"Failed to export output file: {e}")
            return None

    @staticmethod
    def _sanitize_target(target: str) -> str:
        """Sanitize a target string for safe use in filenames.

        ``https://example.com:8443/path`` → ``example.com_8443``
        ``192.168.1.0/24``                → ``192.168.1.0_24``
        """
        if not target:
            return ""
        slug = target
        # Strip protocol and path for URLs
        if re.match(r"^https?://", slug):
            slug = re.sub(r"^https?://", "", slug)
            slug = slug.split("/")[0]  # keep host:port only
        # Replace unsafe chars (/ becomes _ to preserve CIDR notation)
        slug = re.sub(r"[^A-Za-z0-9._-]", "_", slug)
        # Collapse multiple underscores
        slug = re.sub(r"_+", "_", slug).strip("_")
        return slug[:120]  # cap length

    def _store_credentials(self, typed_outputs: list[OutputType]) -> int:
        """Store UserAccount typed outputs in the credential store.

        Returns the number of credentials successfully stored.
        Gracefully handles missing pykeepass or DB file.
        """
        from ofx.runner.services.credential_store import store_from_typed_outputs

        return store_from_typed_outputs(typed_outputs, log_fn=self._log_debug)
