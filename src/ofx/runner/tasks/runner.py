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

logger = logging.getLogger(__name__)


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
    store_creds: bool = Field(
        default=False,
        description="Store discovered UserAccount credentials into the credential store",
    )

    def __str__(self) -> str:
        return f"TaskExecution(task='{self.task_name}', target='{self.target}')"


class TaskRunner(BaseRunner[TaskExecution]):
    """Runner that wraps a :class:`Task` tool definition.

    Lifecycle:
      1. ``_pre_run``  — resolve task from registry, validate it exists
      2. ``_do_run``   — build command, execute, parse output, store typed results
      3. ``_post_run`` — no-op (results already stored)

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
    ):
        super().__init__(model, ctx, parent, None, logger=logger)
        self._task: Task | None = None
        self._output_file: Path | None = None
        self._streamed_items: list[OutputType] = []

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

        # Pre-flight binary check with actionable install hint
        if not self._task.check_installed():
            install_hint = self._task.get_install_command()
            msg = f"Task '{self.model.task_name}' requires '{self._task.cmd}' but it is not installed."
            if install_hint:
                msg += f" Install with: {install_hint}"
            self._log_warning(msg)

        # Apply profile task_options overrides (low priority, user opts win)
        self._apply_profile_task_options()

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
            # Use streaming execution for real-time item parsing
            if self._task.supports_streaming:
                result = await executor.execute_streaming(
                    on_line=self._on_stdout_line,
                )
            else:
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

            # Parse structured output (combines streamed + file-based)
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

            # Auto-store UserAccount credentials if enabled
            if self.model.store_creds and typed_outputs:
                stored = self._store_credentials(typed_outputs)
                if stored:
                    self._log_info(
                        f"Stored {stored} credential(s) in credential store"
                    )

            # Clean up temp output file
            self._cleanup_output_file()

    async def _post_run(self) -> None:
        pass

    # ── Profile integration ────────────────────────────────────────

    def _apply_profile_task_options(self) -> None:
        """Merge profile task_options into the execution opts.

        Profile options are applied as defaults — explicit user options
        from the workflow ``with:`` block always take precedence.
        """
        profile = self.ctx.vars.get("profile")
        if not profile:
            return

        task_options = getattr(profile, "task_options", None) or {}
        overrides = task_options.get(self.model.task_name, {})
        if not overrides:
            return

        merged = dict(overrides)
        merged.update(self.model.opts)  # user opts win
        self.model.opts = merged
        self._log_debug(
            f"Applied profile task_options for '{self.model.task_name}': "
            f"{list(overrides.keys())}"
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
            logger.debug("Channel publish failed (task=%s): %s", self.model.task_name, e)

    def _deduplicate_incremental(
        self, items: list[OutputType]
    ) -> list[OutputType]:
        """Deduplicate against already-streamed items."""
        seen = {item._uuid for item in self._streamed_items}
        new: list[OutputType] = []
        for item in items:
            uid = item._uuid
            if uid not in seen:
                seen.add(uid)
                new.append(item)
        return new

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
            all_items = list(self._streamed_items) + raw
            return self._deduplicate(all_items)
        except Exception as e:
            self._log_warning(f"Output parsing failed: {e}")
            return list(self._streamed_items) if self._streamed_items else []

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

    def _store_credentials(self, typed_outputs: list[OutputType]) -> int:
        """Store UserAccount typed outputs in the credential store.

        Returns the number of credentials successfully stored.
        Gracefully handles missing pykeepass or DB file.
        """
        from ofx.tasks.output_types import UserAccount

        accounts = [o for o in typed_outputs if isinstance(o, UserAccount)]
        if not accounts:
            return 0

        try:
            from ofx.api.creds.exegol_history import ExegolHistoryDB

            db = ExegolHistoryDB()
        except (ImportError, FileNotFoundError) as e:
            self._log_debug(f"Credential store unavailable: {e}")
            return 0

        stored = 0
        for account in accounts:
            if not account.username:
                continue
            try:
                cred = account.to_credential()
                # Skip if an identical credential already exists
                existing = db.get_credential(cred.username)
                if existing and existing.password == cred.password and existing.hash == cred.hash and existing.domain == cred.domain:
                    self._log_debug(
                        f"Credential already exists: {cred.username}"
                    )
                    continue
                db.add_credential(
                    username=cred.username,
                    password=cred.password,
                    hash_value=cred.hash,
                    domain=cred.domain,
                    comment=cred.comment,
                )
                stored += 1
            except Exception as e:
                self._log_debug(f"Failed to store credential for {account.username}: {e}")
        return stored
