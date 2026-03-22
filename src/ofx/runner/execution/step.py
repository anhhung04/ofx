"Step runner for executing workflow steps"

import asyncio
import base64
from datetime import datetime
from pathlib import Path
from random import uniform
from typing import Any

from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import BaseRunner, RunContext, RunnerRegistryKeys, RunnerStatus
from ofx.runner.core.models import RunResult
from ofx.runner.execution.error_helpers import (
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)
from ofx.runner.execution.execution_results import StepExecutionResult
from ofx.runner.logging import get_logger

logger = get_logger()


class StepRunner(BaseRunner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: BaseRunner[Job],
    ):
        super().__init__(step, context, parent, parent.registry)

    async def _pre_run(self) -> None:
        """Prepare the step for execution, resolve templates"""
        self._run_type = self.model.get_run_type()
        resolve_fields = [
            "name",
            "shell",
            "working_directory",
            "log_stdout",
            "env",
            "run_if",
        ]
        match self._run_type:
            case RunType.WORKFLOW:
                resolve_fields.extend(["uses"])
            case RunType.SCRIPT:
                resolve_fields.extend(["script"])
            case RunType.COMMAND:
                resolve_fields.extend(["run"])
            case RunType.SCRIPT_FILE:
                resolve_fields.extend(["script_file"])
            case RunType.TASK:
                resolve_fields.extend(["task", "run_with"])
        await self._resolve_template_fields(resolve_fields)

        if not self._evaluate_run_if(self.model.run_if, self._run_if_context()):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise Exception("Step skipped due to run_if condition")

        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        self.ctx.inputs.update(await self._resolve_template(self.model.run_with))
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
        )

    async def _do_run(self) -> None:
        """
        Execute the step's action with retry logic, timeout handling.
        """
        max_attempts = self.model.retry + 1
        timeout_seconds = self.model.timeout * 60

        last_res = None

        for attempt in range(max_attempts):
            try:
                runner = self._create_runner()
                res = await asyncio.wait_for(runner.run(), timeout=timeout_seconds)
                last_res = res

                if runner.is_success:
                    await self._apply_run_result(res)
                    self._log_debug(f"result: {await self.get_result()}")
                else:
                    raise RuntimeError(step_execution_error(res.status, res.error))
            except TimeoutError as e:
                raise RuntimeError(step_timeout_error(self.model.timeout)) from e
            except Exception as e:
                if attempt < max_attempts - 1:
                    next_delay = self._retry_delay_seconds(
                        attempt=attempt,
                        base_delay=self.model.retry_delay,
                    )
                    self._log_info(
                        f"Retrying in {next_delay:.2f}s (attempt {attempt + 2}/{max_attempts})..."
                    )
                    await asyncio.sleep(next_delay)
                else:
                    if last_res:
                        await self._apply_run_result(last_res)
                        if last_res.status != RunnerStatus.COMPLETED:
                            raise RuntimeError(
                                step_retry_error(max_attempts, last_res.error)
                            ) from e
                    else:
                        raise RuntimeError(step_retry_error(max_attempts, e)) from e

        self._log_debug(f"Final result after retries: {await self.get_result()}")

    async def _post_run(self) -> None:
        """Log stdout/stderr to console, save to file if configured."""
        result = await self.get_result()
        stdout = result.outputs.get("stdout", "")
        stderr = result.outputs.get("stderr", "")

        self._log_output("stdout", stdout)
        self._log_output("stderr", stderr)

        if self.model.log_stdout and stdout and self.ctx.output_path:
            self._save_output_file(stdout, result.outputs)

        status_value = (
            RunnerStatus.COMPLETED.value
            if result.status == RunnerStatus.FINISHED
            else result.status.value
        )
        execution = StepExecutionResult(
            step_index=self.model.step_index,
            name=self.model.name,
            run_type=self._run_type.value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

    def _log_output(self, stream: str, content: str) -> None:
        """Log a stdout/stderr stream to the console."""
        if not content or not isinstance(content, str):
            return
        self._log_info(f"\n==={stream}===\n{content}===========")

    def _save_output_file(self, stdout: str, outputs: dict) -> None:
        """Persist full stdout to a log file under output_path/logs/."""
        if not self.ctx.output_path:
            self._log_warning("No output_path configured, skipping log file save.")
            return
        log_path = self.ctx.output_path / "logs"
        log_path.mkdir(parents=True, exist_ok=True)
        if not self.parent:
            return
        step_name = (self.model.name or f"step_{self.model.step_index}").replace(
            " ", "-"
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = (
            log_path / f"stdout_{self.parent.model.jid}_{step_name}__{timestamp}.log"
        )

        header = []
        if self.model.run:
            header.append(f">> command: {self.model.run}")
        elif self.model.uses:
            header.append(f">> workflow: {self.model.uses}")
        elif self.model.script_file:
            header.append(f">> script_file: {self.model.script_file}")
        elif self.model.script:
            header.append(
                f">> script (base64): {base64.b64encode(self.model.script.encode()).decode()}"
            )
        elif self.model.task:
            header.append(f">> task: {self.model.task}")
        else:
            header.append(">> unknown step type")
        if outputs.get("binary_output"):
            header.append("[BINARY OUTPUT]")
        if outputs.get("output_truncated"):
            header.append("[OUTPUT TRUNCATED]")
        if outputs.get("stderr_truncated"):
            header.append("[STDERR TRUNCATED]")
        header.append(">>===<<")
        out_file.write_text("\n".join(header) + "\n" + stdout)
        self._log_info(f"Saved output to {out_file}")

    def _create_runner(self) -> BaseRunner:
        """Creates the appropriate runner instance based on the step's run type."""
        is_interactive = self.model.interactive and self.ctx.allow_interactive

        if is_interactive and self._run_type == RunType.WORKFLOW:
            self._log_warning(
                "Interactive mode is not supported for workflow steps ('uses'). Ignoring interactive flag."
            )
            is_interactive = False

        if self._run_type is RunType.WORKFLOW:
            from ofx.runner.execution.workflow import WorkflowRunner
            from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

            workflow_dirs = (
                self.ctx.workflow_dirs.copy() if self.ctx.workflow_dirs else []
            )

            workflow = find_workflow(
                self.model.uses or "",
                tuple(workflow_dirs),
                self.parent.model.defaults.flow_registry_url,  # type: ignore
            )

            return WorkflowRunner(
                workflow,
                self._child_context(
                    update={
                        "workflow_dirs": add_workflow_dir(
                            workflow_dirs, workflow.workflow_path.parent
                        ),
                    }
                ),
                parent=self,
            )
        elif self._run_type is RunType.SCRIPT:
            from ofx.runner.commands.command import Script, ScriptRunner

            assert self.model.script is not None, (
                "Script cannot be None for SCRIPT run type"
            )
            script_model = Script(
                script=self.model.script,
                shell=self.model.shell,
                working_directory=self.model.working_directory,
                timeout_minutes=self.model.timeout,
                interactive=self.model.interactive,
            )
            return ScriptRunner(
                script_model,
                self._child_context(),
                parent=self,
            )
        elif self._run_type is RunType.COMMAND:
            from ofx.runner.commands.command import Command, CommandRunner

            assert self.model.run is not None, "Run cannot be None for COMMAND run type"
            cmd = Command(
                cmd=self.model.run,
                shell=self.model.shell,
                working_directory=self._resolve_working_dir(),
                timeout_minutes=self.model.timeout,
                interactive=is_interactive,
            )
            return CommandRunner(
                cmd,
                self._child_context(),
                parent=self,
            )
        elif self._run_type is RunType.SCRIPT_FILE:
            from ofx.runner.commands.command import Script, ScriptRunner

            assert self.model.script_file is not None, (
                "script_file cannot be None for SCRIPT_FILE run type"
            )

            script_path = (
                Path(self.model.script_file.strip()).expanduser().with_suffix(".py")
            )

            if not script_path.is_absolute():
                base_dir = getattr(self.ctx, "workflow_dir", Path.cwd())
                script_path = (base_dir / script_path).resolve()

            if not script_path.exists():
                raise FileNotFoundError(f"Script file '{script_path}' does not exist.")

            script_content = script_path.read_text()
            script_model = Script(
                script=script_content,
                shell=self.model.shell,
                working_directory=self.model.working_directory,
                timeout_minutes=self.model.timeout,
                interactive=self.model.interactive,
            )

            return ScriptRunner(
                script_model,
                self._child_context(),
                parent=self,
            )

        elif self._run_type is RunType.TASK:
            from ofx.runner.tasks.runner import TaskExecution, TaskRunner

            assert self.model.task is not None, (
                "task cannot be None for TASK run type"
            )

            # Extract target from run_with; remaining keys are task options
            task_opts = dict(self.model.run_with)
            target = str(task_opts.pop("target", task_opts.pop("targets", "")))

            task_model = TaskExecution(
                task_name=self.model.task,
                target=target,
                opts=task_opts,
                shell=self.model.shell,
                working_directory=self._resolve_working_dir(),
                timeout_minutes=self.model.timeout,
            )
            return TaskRunner(
                task_model,
                self._child_context(),
                parent=self,
            )

        else:
            raise ValueError(
                f"Invalid run type '{self._run_type}' for step '{self.model.name}'."
            )

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        step_idx = (
            str(self.model.step_index) if hasattr(self.model, "step_index") else "?"
        )
        msg = f"'step{step_idx}' › {msg}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _run_if_context(self) -> dict[str, Any]:
        prev_runner = None
        if self.parent and self.model.step_index > 0:
            prev_runner = self.parent._runners.get(str(self.model.step_index - 1))

        if not prev_runner:
            return {
                "success": lambda: True,
                "failure": lambda: False,
                "canceled": lambda: False,
                "always": lambda: True,
            }

        return {
            "success": lambda: prev_runner.is_success,
            "failure": lambda: prev_runner.is_failed,
            "canceled": lambda: prev_runner.status == RunnerStatus.CANCELED,
            "always": lambda: True,
        }

    async def _apply_run_result(self, res: RunResult) -> None:
        self._error = res.error
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, res.outputs)
        await self.reg_set(
            RunnerRegistryKeys.RESULT, res.model_dump(exclude={"outputs"})
        )

    def _retry_delay_seconds(self, attempt: int, base_delay: int) -> float:
        """Compute exponential backoff with jitter capped to 5 minutes."""
        backoff = base_delay * (2**attempt)
        delay = min(backoff, 300)
        return delay * uniform(0.5, 1.0)

    def _resolve_working_dir(self) -> Path:
        step = self.model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path

        base_path = self.ctx.vars.get("working_directory", Path.cwd())

        return (base_path / step_path).resolve()
