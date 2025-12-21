import logging

from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any, TYPE_CHECKING

from ofx.models.step import Step
from ofx.runner.base import BaseRunner, RunContext, RunnerStatus
from ofx.runner.executors.command import CommandExecutor, ScriptExecutor
from ofx.settings import settings

if TYPE_CHECKING:
    from ofx.runner.job import JobRunner

logger = logging.getLogger(settings.app_branding)

DEFAULT_SHELL = "/bin/bash"


class RunType(Enum):
    SCRIPT = "script"
    COMMAND = "command"
    WORKFLOW = "workflow"


class StepRunner(BaseRunner):
    def __init__(
        self, step: Step, context: RunContext, parent: BaseRunner | None = None
    ):
        super().__init__(step, context, parent)
        self._model = step

    async def _pre_run(self):
        # Register hooks from model
        self._register_hooks_from_model()
        
        self._run_type = self._parse_run_type()
        self._resolve_template_fields(
            [
                "run",
                "run_if",
                "run_with",
                "uses",
                "script",
                "shell",
                "log_stdout",
                "working_directory",
            ]
        )

        self._result.metadata.update({"step": self._model})
        
        # Execute pre_run hooks
        await self._execute_pre_run_hooks()

        if not self._safe_eval(self._model.run_if, "step run_if"):
            self._status = RunnerStatus.CANCELED
            # Execute ON_SKIP hook
            from ofx.runner.core.hooks import HookPoint, HookContext
            hook_ctx = HookContext(
                model=self._model,
                skip_reason="run_if condition not met",
                runner=self,
            )
            await self._hook_handler.execute_hooks(HookPoint.ON_SKIP, hook_ctx)
            raise Exception("Step skipped due to run_if condition")

    async def _post_run(self):
        stdout = self._result.outputs.get("stdout", "")
        if self.model.log_stdout:
            logger.info(self._produce_log(f"stdout:\n{stdout}\n"))
        else:
            tmp_file = (
                self.ctx_vars.output_path
                / f"stdout_{str(self.parent.model.name).replace(' ','_')}_{str(self.model.name).replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            logger.info(
                f"Saving output to {tmp_file}"
            )
            tmp_file.write_text(stdout)
        
        # Execute post_run hooks
        await self._execute_post_run_hooks()
        
        logger.debug(self._produce_log(f"result: {self._result}"))

    def _get_job_defaults(self):
        """Safely get job defaults from parent."""
        from ofx.runner.job import JobRunner
        if self.parent and isinstance(self.parent, JobRunner):
            return self.parent.model.defaults
        return None

    def _get_workflow_defaults(self):
        """Safely get workflow defaults from grandparent."""
        from ofx.runner.workflow import WorkflowRunner
        if self.parent and self.parent.parent and isinstance(self.parent.parent, WorkflowRunner):
            return self.parent.parent.model.defaults
        return None

    async def _do_run(self):
        """Execute step with retry mechanism."""
        max_attempts = self.model.max_attempts
        attempt = 0
        last_error = None
        
        while attempt < max_attempts:
            try:
                await self._execute_step()
                return  # Success, exit retry loop
            except Exception as e:
                attempt += 1
                last_error = e
                
                if attempt < max_attempts:
                    # Execute ON_RETRY hook before retrying
                    from ofx.runner.core.hooks import HookPoint, HookContext
                    hook_ctx = HookContext(
                        model=self._model,
                        error=e,
                        retry_count=attempt,
                        runner=self,
                        inputs=self.ctx_vars.inputs,
                    )
                    await self._hook_handler.execute_hooks(HookPoint.ON_RETRY, hook_ctx)
                    logger.warning(
                        self._produce_log(
                            f"Retry attempt {attempt}/{max_attempts - 1} after error: {e}"
                        )
                    )
                else:
                    # Max attempts reached, re-raise the error
                    raise e
    
    async def _execute_step(self):
        """Execute the actual step logic."""
        if self._run_type is RunType.WORKFLOW:
            from ofx.runner.workflow import WorkflowRunner
            from ofx.runner.loaders.workflow_loader import WorkflowLoader

            # Get output path from context or parent
            output_path = self.ctx_vars.output_path
            if self.parent and self.parent.parent:
                output_path = self.parent.parent.ctx_vars.output_path
            
            runner = WorkflowRunner(
                WorkflowLoader.find_flow(self._model.uses or ""),
                RunContext(
                    inputs=self._resolve_template(self._model.run_with),
                    envs=self.ctx_vars.envs,
                    output_path=output_path,
                    secrets=(
                        self.ctx_vars.secrets
                        if self.model.secrets == "inherit"
                        else self._resolve_template(self.model.secrets)
                    ),
                ),
                parent=self,
            )
        elif self._run_type is RunType.SCRIPT:
            assert (
                self.model.script is not None
            ), "Script cannot be None for SCRIPT run type"
            shell = self.model.get_shell(self._get_job_defaults(), self._get_workflow_defaults())
            executor = ScriptExecutor(
                self.model.script,
                self.ctx_vars.model_copy(),
                self,
                shell=shell,
                working_dir=self._resolve_working_dir(),
                timeout_minutes=self.model.timeout,
            )
            result_data = await executor.execute()
            self._result.outputs.update(result_data)
            return
        elif self._run_type is RunType.COMMAND:
            assert self.model.run is not None, "Run cannot be None for COMMAND run type"
            shell = self.model.get_shell(self._get_job_defaults(), self._get_workflow_defaults())
            executor = CommandExecutor(
                self.model.run,
                self.ctx_vars.model_copy(),
                self,
                shell=shell,
                working_dir=self._resolve_working_dir(),
                timeout_minutes=self.model.timeout,
            )
            result_data = await executor.execute()
            self._result.outputs.update(result_data)
            return
        
        res = await runner.run()
        self._status = res.status
        self._error = res.error
        for k, v in res.model_dump().items():
            setattr(self._result, k, v)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))

    def _produce_log(self, message: Any) -> str:
        step_index = self._model.step_index
        msg = f"{{'{step_index}'}} -> {message}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def _parse_run_type(self) -> RunType:
        step = self._model
        step_name = step.name
        if step.script:
            return RunType.SCRIPT
        elif step.run:
            return RunType.COMMAND
        elif step.uses:
            return RunType.WORKFLOW
        else:
            raise ValueError(
                self._produce_log(
                    f"Step '{step_name}' does not define a valid run type. "
                    "Step must include one of: 'script', 'run', or 'uses'."
                )
            )

    def _resolve_working_dir(self) -> Path:
        """Resolve working directory using model method."""
        return self._model.get_working_directory(self._get_job_defaults(), self._get_workflow_defaults())

    @property
    def model(self) -> Step:
        return self._model

    @property
    def parent(self) -> "JobRunner":
        if not self._parent:
            raise ValueError("orphan StepRunner detected - parent JobRunner is None")
        from ofx.runner.job import JobRunner
        assert isinstance(self._parent, JobRunner)
        return self._parent