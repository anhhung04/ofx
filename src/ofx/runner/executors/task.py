"""Executor for registered task steps."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from ofx.models.command import Command
from ofx.runner.commands.command import CommandRunner
from ofx.runner.commands.command_executor import CommandExecutionResult, CommandExecutor
from ofx.runner.context import RunContext, context_with_env
from ofx.runner.executors.base import Executor
from ofx.runner.registry_keys import RunnerRegistryKeys
from ofx.runner.task_profile_options import adapt_task_command_for_profile
from ofx.runner.task_step import extract_output_item_target
from ofx.settings import TOOLS_BIN_DIR
from ofx.tasks.registry import TaskRegistry
from ofx.utils.file_cleanup import remove_file

logger = logging.getLogger(__name__)

class TaskExecutor(Executor):
    """Execution strategy for [`TaskRunner`](src/ofx/runner/tasks/runner.py)."""

    async def pre_run(self, runner) -> None:
        task_cls = TaskRegistry.get(runner.model.task_name)
        if task_cls is None:
            available = ", ".join(TaskRegistry.list_tasks()) or "(none)"
            raise RuntimeError(
                f"Task '{runner.model.task_name}' is not registered. Available tasks: {available}"
            )

        runner._task = task_cls()
        task = runner._task
        try:
            if task.check_installed():
                return

            install_cmd = task.get_install_command()
            if not install_cmd:
                runner._log_warning(
                    f"Task '{runner.model.task_name}' requires '{task.cmd}' "
                    "but it is not installed and no install command is defined."
                )
                return

            runner._log_info(
                f"Tool '{task.cmd}' not found - auto-installing with: {install_cmd}"
            )
            command_runner = CommandRunner(
                Command(cmd=install_cmd),
                context_with_env(RunContext(), runner.ctx.envs),
            )
            result = await command_runner.run()

            if result.status.value != "completed":
                runner._log_warning(f"Auto-install of '{task.cmd}' failed: {result.error}")
            elif shutil.which(task.cmd) or (TOOLS_BIN_DIR / task.cmd).exists():
                runner._log_info(f"Tool '{task.cmd}' installed successfully")
            else:
                runner._log_warning(
                    f"Install command succeeded but '{task.cmd}' still not found on PATH"
                )
        except Exception as exc:
            runner._log_warning(f"Auto-install of '{task.cmd}' error: {exc}")
        finally:
            runner._apply_profile_task_options()

    async def do_run(self, runner) -> None:
        task = getattr(runner, "_task", None)
        assert task is not None, "runner._task must be set before executing a task"
        model = runner.model
        outputs: dict[str, Any] = {}
        await runner.reg_set(RunnerRegistryKeys.OUTPUTS, outputs)

        command, runner._output_file = task.build_command(
            model.target,
            **model.opts,
        )
        command = adapt_task_command_for_profile(
            command,
            task_declared_opts=getattr(task, "opts", {}),
            resolved_opts=model.opts,
            profile=runner.ctx.vars.get("profile_model"),
        )
        runner._log_info(f"Command: {command}")

        executor = CommandExecutor(
            Command(
                cmd=command,
                shell=model.shell,
                working_directory=model.working_directory,
                timeout_minutes=model.timeout_minutes,
            ),
            runner.ctx.envs,
        )
        executor.prepare_outputs_file()
        result: CommandExecutionResult | None = None

        try:
            if task.supports_streaming:
                result = await executor.execute_streaming(
                    on_line=runner._on_stdout_line
                )
            else:
                result = await executor.execute()

            exit_code = result.exit_code
            if exit_code is not None and exit_code not in task.success_codes:
                stderr = result.stderr or f"Command failed with exit code {exit_code}"
                raise RuntimeError(f"Command failed: {stderr}")
        except TimeoutError:
            raise RuntimeError(
                f"Task '{model.task_name}' timed out after "
                f"{model.timeout_minutes} minutes"
            ) from None
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Task '{model.task_name}' error: {exc}") from exc
        finally:
            await self._finalize_task_execution(
                runner,
                outputs=outputs,
                command=command,
                executor=executor,
                result=result,
            )

    async def _finalize_task_execution(
        self,
        runner,
        *,
        outputs: dict[str, Any],
        command: str,
        executor: CommandExecutor,
        result: CommandExecutionResult | None,
    ) -> None:
        final_result = result or CommandExecutionResult(
            exit_code=None,
            stdout="",
            stderr="",
            outputs={},
        )
        typed_outputs = runner._parse_outputs(final_result)

        outputs.update(
            {
                "exit_code": final_result.exit_code,
                "stdout": final_result.stdout,
                "stderr": final_result.stderr,
            }
        )
        outputs.update(final_result.outputs)
        typed_output_dicts = [item.to_dict() for item in typed_outputs]
        if runner.model.target:
            if not Path(runner.model.target).is_file():
                for item_dict in typed_output_dicts:
                    item_dict["_target"] = runner.model.target
            else:
                for item_dict in typed_output_dicts:
                    item_target = extract_output_item_target(item_dict)
                    if item_target:
                        item_dict["_target"] = item_target
        outputs.update(
            {
                "command": command,
                "typed_outputs": typed_output_dicts,
            }
        )
        output_file_path: str | None = None
        if runner._task.export_output:
            exported_path = runner._export_output_file()
            if exported_path:
                output_file_path = str(exported_path)
            exc = remove_file(runner._output_file)
            if isinstance(exc, OSError):
                logger.debug(
                    "Failed to remove task output file %s: %s",
                    runner._output_file,
                    exc,
                )
        elif runner._output_file and runner._output_file.exists():
            output_file_path = str(runner._output_file)

        if output_file_path:
            outputs["output_file"] = output_file_path

        await runner.reg_update(RunnerRegistryKeys.OUTPUTS, outputs)
        await executor.capture_outputs_file(
            runner,
            RunnerRegistryKeys.OUTPUTS,
            runner._log_debug,
        )
        if runner.model.store_creds and typed_outputs:
            from ofx.runner.services.credential_store import store_and_log_typed_outputs

            store_and_log_typed_outputs(
                typed_outputs,
                debug_fn=runner._log_debug,
                info_fn=runner._log_info,
            )

    async def post_run(self, runner) -> None:
        pass

__all__ = ["TaskExecutor"]
