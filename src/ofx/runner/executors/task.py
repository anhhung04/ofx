"""Executor for registered task steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.models.command import Command
from ofx.runner.commands.command import CommandRunner
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.context import build_env_context
from ofx.runner.executors.base import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.settings import TOOLS_BIN_DIR
from ofx.tasks.registry import TaskRegistry


class TaskExecutor(Executor):
    """Execution strategy for [`TaskRunner`](src/ofx/runner/tasks/runner.py)."""

    async def pre_run(self, runner) -> None:
        task_cls = TaskRegistry.get(runner.model.task_name)
        if task_cls is None:
            available = ", ".join(TaskRegistry.list_tasks()) or "(none)"
            raise RuntimeError(
                f"Task '{runner.model.task_name}' is not registered. "
                f"Available tasks: {available}"
            )
        runner._task = task_cls()

        if not runner._task.check_installed():
            install_cmd = runner._task.get_install_command()
            if install_cmd:
                await self._auto_install_tool(runner, runner._task.cmd, install_cmd)
            else:
                runner._log_warning(
                    f"Task '{runner.model.task_name}' requires '{runner._task.cmd}' "
                    "but it is not installed and no install command is defined."
                )

        runner._apply_profile_task_options()

    @staticmethod
    def _make_command_runner(command: str, env: dict[str, Any]) -> CommandRunner:
        """Create an isolated command runner with the provided environment."""
        return CommandRunner(Command(cmd=command), build_env_context(env))

    async def do_run(self, runner) -> None:
        assert runner._task is not None

        outputs: dict[str, Any] = {}
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)

        cmd_str, runner._output_file = runner._task.build_command(
            runner.model.target, **runner.model.opts
        )
        runner._log_info(f"Command: {cmd_str}")

        cmd_model = Command(
            cmd=cmd_str,
            shell=runner.model.shell,
            working_directory=runner.model.working_directory,
            timeout_minutes=runner.model.timeout_minutes,
        )
        executor = CommandExecutor(cmd_model, runner.ctx.envs)
        executor.prepare_outputs_file()
        result: CommandExecutionResult | None = None

        try:
            if runner._task.supports_streaming:
                result = await executor.execute_streaming(on_line=runner._on_stdout_line)
            else:
                result = await executor.execute()

            exit_code = result.exit_code
            if exit_code is not None and exit_code not in runner._task.success_codes:
                stderr = result.stderr or f"Command failed with exit code {exit_code}"
                raise RuntimeError(f"Command failed: {stderr}")
        except TimeoutError:
            raise RuntimeError(
                f"Task '{runner.model.task_name}' timed out after "
                f"{runner.model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Task '{runner.model.task_name}' error: {exc}") from exc
        finally:
            if result is None:
                result = CommandExecutionResult(
                    exit_code=None, stdout="", stderr="", outputs={}
                )

            typed_outputs = runner._parse_outputs(result)
            typed_dicts = self._build_typed_output_dicts(runner, typed_outputs)

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
            await runner.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)

            await executor.capture_outputs_file(
                runner,
                RunnerRegistryKeys.OUTPUTS,
                lambda msg: runner._log_debug(msg),
            )

            if runner.model.store_creds and typed_outputs:
                stored = runner._store_credentials(typed_outputs)
                if stored:
                    runner._log_info(f"Stored {stored} credential(s) in credential store")

            if runner._task.export_output:
                exported_path = runner._export_output_file()
                if exported_path:
                    outputs["output_file"] = str(exported_path)
                    await runner.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)
                runner._cleanup_output_file()
            else:
                if runner._output_file and runner._output_file.exists():
                    outputs["output_file"] = str(runner._output_file)
                    await runner.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)

    async def post_run(self, runner) -> None:
        if runner._task is not None:
            runner._task.cleanup_target_files()

    async def _auto_install_tool(self, runner, tool_bin: str, install_cmd: str) -> None:
        runner._log_info(
            f"Tool '{tool_bin}' not found - auto-installing with: {install_cmd}"
        )
        try:
            command_runner = self._make_command_runner(install_cmd, runner.ctx.envs)
            result = await command_runner.run()

            if result.status.value != "completed":
                runner._log_warning(
                    f"Auto-install of '{tool_bin}' failed: {result.error}"
                )
                return

            tool_path = TOOLS_BIN_DIR / tool_bin
            import shutil

            if shutil.which(tool_bin) or tool_path.exists():
                runner._log_info(f"Tool '{tool_bin}' installed successfully")
            else:
                runner._log_warning(
                    f"Install command succeeded but '{tool_bin}' still not found on PATH"
                )
        except Exception as exc:
            runner._log_warning(f"Auto-install of '{tool_bin}' error: {exc}")

    def _build_typed_output_dicts(self, runner, typed_outputs) -> list[dict[str, Any]]:
        target_tag = runner.model.target
        target_is_file = target_tag and Path(target_tag).is_file()
        typed_dicts: list[dict[str, Any]] = []
        for output in typed_outputs:
            item = output.to_dict()
            if target_is_file:
                item_target = self._extract_item_target(item)
                if item_target:
                    item["_target"] = item_target
            elif target_tag:
                item["_target"] = target_tag
            typed_dicts.append(item)
        return typed_dicts

    @staticmethod
    def _extract_item_target(item: dict[str, Any]) -> str:
        for key in ("domain", "host", "ip"):
            value = item.get(key, "")
            if value:
                return value
        url = item.get("url", "")
        if url:
            from urllib.parse import urlparse

            try:
                return urlparse(url).hostname or ""
            except Exception:
                return ""
        return ""


__all__ = ["TaskExecutor"]
