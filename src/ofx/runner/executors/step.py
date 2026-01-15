"Step runner for executing workflow steps"

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from ofx.models.step import Step
from ofx.runner.core import BaseRunner, RunContext, RunnerStatus, RunType
from ofx.runner.lifecycle import HookManager
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class StepRunner(BaseRunner):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(step, context, parent)
        self._model = step
        self._hook_manager = HookManager(self)

    async def _run_hook(self, hook_name: str) -> None:
        """Executes a lifecycle hook if it's defined in the step."""
        await self._hook_manager.run_hook(
            hook_name,
            self.model.hooks,
            self.model.shell,
            self._resolve_working_dir(),
            self.ctx_vars,
        )

    async def _pre_run(self) -> None:
        """Prepare the step for execution, resolve templates, and run 'before_step' hook."""
        await self._run_hook("before_step")
        self._run_type = self._parse_run_type()
        await self._resolve_template_fields(
            [
                "run",
                "run_if",
                "run_with",
                "uses",
                "script",
                "script_file",
                "shell",
                "log_stdout",
                "log_stdout",
                "working_directory",
                "secrets",
            ]
        )
        self._result.metadata.update({"step": self._model})
        if not self._model.run_if:
            self._status = RunnerStatus.CANCELED
            await self._run_hook("on_skip")
            raise Exception("Step skipped due to run_if condition")

    async def _post_run(self) -> None:
        """Log stdout, save output if configured, and run 'after_step' hook."""
        if self._error:
            logger.error(self._produce_log(f"step failed: {self._error}"))
            for handler in logger.handlers:
                handler.flush()

        result = self.get_result()
        stdout = result.outputs.get("stdout", "")
        is_binary = result.outputs.get("binary_output", False)
        is_truncated = result.outputs.get("output_truncated", False)
        stderr_truncated = result.outputs.get("stderr_truncated", False)

        if stdout and isinstance(stdout, str):
            msg_parts = ["stdout:"]
            if is_binary:
                msg_parts.append("[BINARY OUTPUT - base64 encoded]")
            if is_truncated:
                msg_parts.append("[OUTPUT TRUNCATED]")
            if stderr_truncated:
                msg_parts.append("[STDERR TRUNCATED]")

            log_msg = " ".join(msg_parts) + f"\n{stdout}"
            logger.info(self._produce_log(log_msg))
            for handler in logger.handlers:
                handler.flush()

            if self.model.log_stdout:
                log_path = self.ctx_vars.output_path / "logs"
                log_path.mkdir(parents=True, exist_ok=True)
                tmp_file = (
                    log_path
                    / f"stdout_{self.parent.model.jid}_{self.model.name.replace(' ', '-')}__{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                logger.info(
                    self._produce_log(f"Saving output of '{self.parent.model.jid}'[{self.model.step_index}] to {tmp_file}")
                )
                async with aiofiles.open(tmp_file, "w") as f:
                    await f.write(f"cmd: {self.model.run or self.model.script or self.model.uses}\n")
                    if is_binary:
                        await f.write("[BINARY OUTPUT - base64 encoded]\n")
                    if is_truncated:
                        await f.write("[OUTPUT TRUNCATED]\n")
                    if stderr_truncated:
                        await f.write("[STDERR TRUNCATED]\n")
                    await f.write("===\n")
                    await f.write(stdout)
        logger.debug(self._produce_log(f"result: {self._result}"))
        await self._run_hook("after_step")

    async def _do_run(self) -> None:
        """
        Execute the step's action with retry logic, timeout handling, and lifecycle hooks.
        """
        max_attempts = getattr(self.model, "retry", 0) + 1
        delay = getattr(self.model, "retry_delay", 5)
        timeout_seconds = self.model.timeout * 60

        last_res = None

        for attempt in range(max_attempts):
            try:
                runner = self._create_runner()
                res = await asyncio.wait_for(runner.run(), timeout=timeout_seconds)
                last_res = res

                if res.status == RunnerStatus.COMPLETED:
                    self._apply_run_result(res)
                    logger.debug(self._produce_log(f"result: {self.get_result()}"))
                    return

                raise Exception(f"Step execution failed with status: {res.status}, error: {res.error}")

            except TimeoutError:
                self._status = RunnerStatus.FAILED
                self._error = f"Step timed out after {self.model.timeout} minutes."
                logger.error(self._produce_log(self._error))
                await self._run_hook("on_timeout")
                break
            except Exception as e:
                logger.error(
                    self._produce_log(
                        f"Step failed on attempt {attempt + 1}/{max_attempts}. Error: {e}"
                    )
                )
                if attempt < max_attempts - 1:
                    await self._run_hook("on_retry")
                    logger.info(self._produce_log(f"Retrying in {delay}s..."))
                    await asyncio.sleep(delay)
                else:
                    if last_res:
                        self._apply_run_result(last_res)
                        if not self._error:
                            self._error = str(e)
                    else:
                        self._status = RunnerStatus.FAILED
                        self._error = str(e)

        logger.debug(self._produce_log(f"Final result after retries: {self.get_result()}"))

    def _create_runner(self) -> BaseRunner:
        """Creates the appropriate runner instance based on the step's run type."""
        is_interactive = self.model.interactive and self.ctx_vars.allow_interactive

        if is_interactive and self._run_type == RunType.WORKFLOW:
            logger.warning(
                self._produce_log(
                    "Interactive mode is not supported for workflow steps ('uses'). Ignoring interactive flag."
                )
            )
            is_interactive = False

        if self._run_type is RunType.WORKFLOW:
            from ofx.runner.executors.workflow import WorkflowRunner
            from ofx.utils.misc import add_workflow_dir, find_workflow

            output_path = Path.cwd()
            workflow_dirs = self.ctx_vars.workflow_dirs.copy() if self.ctx_vars.workflow_dirs else []

            parent = getattr(self, "parent", None)
            if parent and getattr(parent, "parent", None):
                output_path = getattr(
                    parent.parent.ctx_vars, "output_path", Path.cwd()
                )
                if hasattr(parent.parent.ctx_vars, 'workflow_dirs'):
                    workflow_dirs = parent.parent.ctx_vars.workflow_dirs.copy()

            flow_path, workflow = find_workflow(
                self._model.uses or "",
                tuple(workflow_dirs)
            )

            if Path(self._model.uses or "").exists():
                workflow_dirs = add_workflow_dir(
                    workflow_dirs,
                    flow_path.parent
                )

            return WorkflowRunner(
                workflow,
                RunContext(
                    inputs=self.model.run_with,
                    envs=self.ctx_vars.envs,
                    output_path=output_path,
                    secrets=(
                        self.ctx_vars.secrets
                        if self.model.secrets == "inherit"
                        else self.model.secrets
                    ),
                    workflow_dirs=workflow_dirs,
                    workflow_dir=flow_path.parent,
                ),
                parent=self,
            )
        elif self._run_type is RunType.SCRIPT:
            from ofx.runner.executors.command import ScriptRunner
            
            assert self.model.script is not None, "Script cannot be None for SCRIPT run type"
            return ScriptRunner(
                self.model.script,
                self.ctx_vars.model_copy(deep=True),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
                interactive=is_interactive,
            )
        elif self._run_type is RunType.COMMAND:
            from ofx.runner.executors.command import CommandRunner
            
            assert self.model.run is not None, "Run cannot be None for COMMAND run type"
            return CommandRunner(
                self.model.run,
                self.ctx_vars.model_copy(deep=True),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
                interactive=is_interactive,
            )
        elif self._run_type is RunType.SCRIPT_FILE:
            import sys
            from ofx.runner.executors.command import CommandRunner

            assert self.model.script_file is not None, "script_file cannot be None for SCRIPT_FILE run type"

            script_path = Path(self.model.script_file.strip()).expanduser()
            if script_path.suffix != ".py":
                script_path = script_path.with_suffix(".py")

            if not script_path.is_absolute():
                base_dir = getattr(self.ctx_vars, "workflow_dir", Path.cwd())
                script_path = (base_dir / script_path).resolve()

            if not script_path.exists():
                raise FileNotFoundError(f"Script file '{script_path}' does not exist.")

            cmd = f"{sys.executable} {script_path.as_posix()}"
            working_dir = script_path.parent

            return CommandRunner(
                cmd,
                self.ctx_vars.model_copy(deep=True),
                shell=self.model.shell,
                working_dir=working_dir,
                parent=self,
                timeout_minutes=self.model.timeout,
                interactive=is_interactive,
            )

        else:
            raise ValueError(f"Invalid run type '{self._run_type}' for step '{self.model.name}'.")

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        step_idx = str(self._model.step_index) if hasattr(self._model, 'step_index') else '?'
        msg = f"'step{step_idx}' › {msg}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _apply_run_result(self, res) -> None:
        self._status = res.status
        self._error = res.error
        for k, v in res.model_dump().items():
            setattr(self._result, k, v)

    def _parse_run_type(self) -> RunType:
        step = self._model
        if step.uses:
            return RunType.WORKFLOW
        elif step.script:
            return RunType.SCRIPT
        elif step.script_file:
            return RunType.SCRIPT_FILE
        elif step.run:
            return RunType.COMMAND
        raise ValueError(
            self._produce_log(
                f"Step '{step.name}' must have one of 'run', 'script', 'script_file', or 'uses' defined."
            )
        )

    def _resolve_working_dir(self) -> Path:
        step = self._model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path

        base_path = self.ctx_vars.vars.get("working_directory", Path.cwd())

        return (base_path / step_path).resolve()


    @property
    def model(self) -> Step:
        return self._model

    @property
    def parent(self) -> "JobRunner": # type: ignore
        return self._parent
