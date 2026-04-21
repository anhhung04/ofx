"""TaskRunner — executes a registered task and stores typed outputs."""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ofx.models.command import Command
from ofx.runner.commands.command import CommandRunner
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys
from ofx.settings import TOOLS_BIN_DIR
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

        # Pre-flight binary check — auto-install if possible
        if not self._task.check_installed():
            install_cmd = self._task.get_install_command()
            if install_cmd:
                await self._auto_install_tool(self._task.cmd, install_cmd)
            else:
                self._log_warning(
                    f"Task '{self.model.task_name}' requires '{self._task.cmd}' "
                    f"but it is not installed and no install command is defined."
                )

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
            # Honour task-specific success codes (e.g. ssh-audit returns 3 for warnings)
            exit_code = result.exit_code
            if exit_code is not None and exit_code not in self._task.success_codes:
                stderr = result.stderr or f"Command failed with exit code {exit_code}"
                raise RuntimeError(f"Command failed: {stderr}")
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

            # Tag each typed output with the task target for per-target grouping.
            # When the target is a file path (list of hosts), derive the
            # per-item target from the item's own fields instead of using the
            # file path which would create meaningless per-target directories.
            target_tag = self.model.target
            target_is_file = target_tag and Path(target_tag).is_file()
            typed_dicts = []
            for o in typed_outputs:
                d = o.to_dict()
                if target_is_file:
                    item_target = _extract_item_target(d)
                    if item_target:
                        d["_target"] = item_target
                elif target_tag:
                    d["_target"] = target_tag
                typed_dicts.append(d)

            # Store regular outputs
            outputs.update(
                {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "command": cmd_str,
                    "typed_outputs": typed_dicts,
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

            # Export output file to output_path with target in filename
            if self._task.export_output:
                exported_path = self._export_output_file()
                if exported_path:
                    outputs["output_file"] = str(exported_path)
                    await self.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)
                # Clean up temp output file (exported copy lives in scans/)
                self._cleanup_output_file()
            else:
                # Intermediate output — keep temp file for subsequent steps
                if self._output_file and self._output_file.exists():
                    outputs["output_file"] = str(self._output_file)
                    await self.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)

    async def _post_run(self) -> None:
        if self._task is not None:
            self._task.cleanup_target_files()

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

        # Layer 1: auto-map common profile fields to task opt names
        if self._task is not None:
            task_opts = self._task.opts  # declared opts for this tool

            from ofx.cloud.task_runtime import _COMMON_MAPPING

            injected: list[str] = []
            for profile_attr, candidate_names in _COMMON_MAPPING:
                value = getattr(profile, profile_attr, None)
                if value is None:
                    continue
                # Skip zero/empty values
                if isinstance(value, (int, float)) and value == 0:
                    continue
                if isinstance(value, str) and not value:
                    continue

                for opt_name in candidate_names:
                    if opt_name in task_opts and opt_name not in self.model.opts:
                        self.model.opts[opt_name] = value
                        injected.append(f"{opt_name}={value}")
                        break  # first matching opt wins

            if injected:
                self._log_debug(
                    f"Injected profile common opts: {', '.join(injected)}"
                )

        # Layer 2: per-task overrides from profile.task_options
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

    # ── Auto-install ──────────────────────────────────────────────

    async def _auto_install_tool(self, tool_bin: str, install_cmd: str) -> None:
        """Attempt to install a missing tool binary using its install_cmd.

        Checks both ``$PATH`` and ``~/Tools/bin`` after install to confirm
        success.  On failure the task continues (the command itself will
        produce a clearer error).
        """
        self._log_info(
            f"Tool '{tool_bin}' not found — auto-installing with: {install_cmd}"
        )
        try:
            cmd_model = Command(cmd=install_cmd)
            runner = CommandRunner(cmd_model, RunContext(envs=self.ctx.envs))
            result = await runner.run()

            if result.status.value != "completed":
                self._log_warning(
                    f"Auto-install of '{tool_bin}' failed: {result.error}"
                )
                return

            # Verify it's now reachable
            tool_path = TOOLS_BIN_DIR / tool_bin
            if shutil.which(tool_bin) or tool_path.exists():
                self._log_info(f"Tool '{tool_bin}' installed successfully")
            else:
                self._log_warning(
                    f"Install command succeeded but '{tool_bin}' still not found on PATH"
                )
        except Exception as e:
            self._log_warning(f"Auto-install of '{tool_bin}' error: {e}")

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
        self, items: Sequence[OutputType]
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
            all_items = list(self._streamed_items) + list(raw)
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
            except OSError as e:
                logger.debug("Failed to remove task output file %s: %s", self._output_file, e)

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
        from ofx.runner.core.credential_store import store_from_typed_outputs

        return store_from_typed_outputs(
            typed_outputs, log_fn=self._log_debug
        )


def _extract_item_target(item: dict[str, Any]) -> str:
    """Derive a meaningful per-item target from the item's own fields.

    Used when the task target is a file path (list of hosts) so we avoid
    creating per-target directories named after temp files.
    """
    for key in ("domain", "host", "ip"):
        val = item.get(key, "")
        if val:
            return val
    url = item.get("url", "")
    if url:
        # Extract hostname from URL
        from urllib.parse import urlparse

        try:
            return urlparse(url).hostname or ""
        except Exception:
            return ""
    return ""
