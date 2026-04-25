"Step runner for executing workflow steps"

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from ofx.models.job import Job
from ofx.models.step import RunType, Step
from ofx.runner.context import RunnerContextBuilder
from ofx.runner.core import (
    BaseRunner,
    ConditionNotMetError,
    RunContext,
    RunnerRegistryKeys,
    RunnerStatus,
)
from ofx.runner.core.models import RunResult
from ofx.runner.execution.error_helpers import (
    step_execution_error,
    step_retry_error,
    step_timeout_error,
)
from ofx.runner.execution.execution_results import (
    build_step_execution_result,
)
from ofx.runner.execution.step_mixin import StepRunnerMixin
from ofx.runner.logging import get_logger


def _timeout_int(value: int | str) -> int:
    """Coerce a template-resolved timeout (may arrive as str) to int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 60 * 24  # default: 24 hours


logger = get_logger()


class StepRunner(StepRunnerMixin, BaseRunner[Step]):
    def __init__(
        self,
        step: Step,
        context: RunContext,
        parent: BaseRunner[Job],
    ):
        super().__init__(step, context, parent, parent.registry)
        self._outputs_file: Path | None = None

    async def _pre_run(self) -> None:
        """Prepare the step for execution, resolve templates"""
        self._apply_retry_profile_defaults()
        self._run_type = self.model.get_run_type()

        # Create outputs file early so {{ env.OFX_OUTPUTS }} resolves in templates
        if self._run_type in (RunType.COMMAND, RunType.SCRIPT, RunType.SCRIPT_FILE):
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_out_", suffix=".txt")
            os.close(fd)
            self._outputs_file = Path(tmp_path)
            self.ctx.envs["RUNNER_OUTPUTS"] = str(self._outputs_file)
            self.ctx.envs["OFX_OUTPUTS"] = str(self._outputs_file)

        resolve_fields = [
            "name",
            "shell",
            "working_directory",
            "log_stdout",
            "log_command",
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

        # Resolve timeout (may be a Jinja2 expression for dynamic scaling)
        await self._resolve_timeout_field()

        if not self._evaluate_run_if(self.model.run_if, self._run_if_context()):
            self._state_machine.transition(RunnerStatus.CANCELED)
            raise ConditionNotMetError("Step skipped due to run_if condition")

        self.ctx = RunnerContextBuilder(self.ctx).with_env(self.model.env)
        self.ctx.inputs.update(await self._resolve_template(self.model.run_with))
        await self.reg_set(
            RunnerRegistryKeys.MODEL,
            self.model.model_dump(exclude={"env", "secrets", "run_with"}),
        )

    async def _on_failure_cleanup(self) -> None:
        """Save execution data and clean up temp outputs file on failure.

        This ensures that steps with ``continue_on_error: true`` still have
        their outputs accessible to later steps via the registry.
        """
        try:
            result = await self.get_result()
            execution = build_step_execution_result(
                step_index=self.model.step_index,
                name=self.model.name,
                run_type=self._run_type.value,
                status=RunnerStatus.FAILED.value,
                error=result.error or self._error,
                outputs=result.outputs,
                duration_ms=self.duration_ms(),
            )
            await self.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())
        except Exception as e:
            self._log_debug(f"Failed to save step execution on failure: {e}")
        if self._outputs_file:
            self._outputs_file.unlink(missing_ok=True)

    async def _do_run(self) -> None:
        """
        Execute the step's action with retry logic, timeout handling.
        """
        max_attempts = self.model.retry + 1
        timeout_seconds = _timeout_int(self.model.timeout) * 60

        last_res = None
        attempt_errors: list[str] = []

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
                raise RuntimeError(
                    step_timeout_error(_timeout_int(self.model.timeout))
                ) from e
            except Exception as e:
                err_msg = str(e)
                attempt_errors.append(f"attempt {attempt + 1}: {err_msg}")
                if attempt < max_attempts - 1:
                    next_delay = self._retry_delay_seconds(
                        attempt=attempt,
                        base_delay=self.model.retry_delay,
                    )
                    self._log_info(
                        f"Retry {attempt + 2}/{max_attempts} in {next_delay:.1f}s — {err_msg}"
                    )
                    await asyncio.sleep(next_delay)
                else:
                    if last_res:
                        await self._apply_run_result(last_res)
                        if last_res.status != RunnerStatus.COMPLETED:
                            raise RuntimeError(
                                step_retry_error(max_attempts, last_res.error)
                                + f"\n  Attempts: {'; '.join(attempt_errors)}"
                            ) from e
                    else:
                        raise RuntimeError(
                            step_retry_error(max_attempts, e)
                            + f"\n  Attempts: {'; '.join(attempt_errors)}"
                        ) from e

        self._log_debug(f"Final result after retries: {await self.get_result()}")

    async def _post_run(self) -> None:
        """Log stdout/stderr to console, save to file if configured."""
        result = await self.get_result()
        stdout = result.outputs.get("stdout", "")
        stderr = result.outputs.get("stderr", "")

        # For task steps with typed outputs, show formatted tables
        if not self._format_typed_outputs(result):
            self._log_output("stdout", stdout)

        self._log_output("stderr", stderr)

        if self.model.log_stdout and stdout and self.ctx.output_path:
            self._save_output_file(stdout, result.outputs)

        status_value = (
            RunnerStatus.COMPLETED.value
            if result.status == RunnerStatus.FINISHED
            else result.status.value
        )
        execution = build_step_execution_result(
            step_index=self.model.step_index,
            name=self.model.name,
            run_type=self._run_type.value,
            status=status_value,
            error=result.error,
            outputs=result.outputs,
            duration_ms=self.duration_ms(),
        )
        await self.reg_set(RunnerRegistryKeys.EXECUTION, execution.to_dict())

        # Cleanup outputs file if it still exists
        if self._outputs_file:
            self._outputs_file.unlink(missing_ok=True)

        # Log to project timeline CSV only when step has explicit log-command config
        if self.model.log_command:
            self._log_timeline(result, status_value)

    def _save_output_file(self, stdout: str, outputs: dict) -> None:
        """Persist full stdout to a log file under output_path/logs/."""
        from ofx.runner.core.step_output import save_output_file

        if not self.ctx.output_path:
            self._log_warning("No output_path configured, skipping log file save.")
            return
        if not self.parent:
            return
        save_output_file(
            self.ctx.output_path,
            self.parent.model.jid,
            self.model,
            stdout,
            outputs,
            log_fn=self._log_info,
        )

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
                timeout_minutes=_timeout_int(self.model.timeout),
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
                timeout_minutes=_timeout_int(self.model.timeout),
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
                timeout_minutes=_timeout_int(self.model.timeout),
                interactive=self.model.interactive,
            )

            return ScriptRunner(
                script_model,
                self._child_context(),
                parent=self,
            )

        elif self._run_type is RunType.TASK:
            from ofx.runner.tasks.runner import TaskExecution, TaskRunner

            assert self.model.task is not None, "task cannot be None for TASK run type"

            # Extract target from run_with; remaining keys are task options
            task_opts = dict(self.model.run_with)
            raw_target = task_opts.pop("target", task_opts.pop("targets", ""))
            # If target is a list (e.g. from unresolved matrix input), join
            # with commas so CLI tools receive a valid argument instead of a
            # Python list repr like "['url1', 'url2']".
            if isinstance(raw_target, list):
                target = ",".join(str(t) for t in raw_target)
            else:
                target = str(raw_target)

            if not target:
                self._log_warning(
                    f"Task '{self.model.task}' has no 'target' in 'with:' — "
                    f"the tool may fail or scan nothing."
                )

            task_model = TaskExecution(
                task_name=self.model.task,
                target=target,
                opts=task_opts,
                shell=self.model.shell,
                working_directory=self._resolve_working_dir(),
                timeout_minutes=_timeout_int(self.model.timeout),
                store_creds=self._resolve_store_creds(),
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

    async def _apply_run_result(self, res: RunResult) -> None:
        self._error = res.error
        await self.reg_set(RunnerRegistryKeys.OUTPUTS, res.outputs)
        await self.reg_set(
            RunnerRegistryKeys.RESULT, res.model_dump(exclude={"outputs"})
        )

    def _log_timeline(self, result: RunResult, status: str) -> None:
        """Write a timeline entry for this step execution."""
        from ofx.runner.execution.timeline import log_step

        params = self._build_timeline_params(result)

        log_step(
            ctx_vars=self.ctx.vars,
            output_path=self.ctx.output_path,
            step_name=self.model.name or f"step{self.model.step_index}",
            status=status,
            duration_ms=self.duration_ms(),
            exit_code=result.outputs.get("exit_code"),
            **params,
        )

    def _resolve_working_dir(self) -> Path:
        step = self.model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path

        base_path = self.ctx.vars.get("working_directory", Path.cwd())

        return (base_path / step_path).resolve()

    def _resolve_store_creds(self) -> bool:
        """Resolve whether to store credentials from task outputs.

        Precedence: step-level > job/workflow defaults > global setting.
        """
        from ofx.runner.core.credential_store import should_store_creds

        parent_model = self.parent.model if self.parent else None
        return should_store_creds(self.model.store_creds, parent_model)
