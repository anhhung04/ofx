"""Step runner for executing workflow steps"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ofx.models.step import Step
from ofx.runner.base import BaseRunner
from ofx.runner.command import CommandRunner, ScriptRunner
from ofx.runner.models import RunContext, RunType, RunnerStatus
from ofx.settings import settings

if TYPE_CHECKING:
    from ofx.runner.workflow import WorkflowRunner

logger = logging.getLogger(settings.app_branding)


class StepRunner(BaseRunner):
    def __init__(
        self, step: Step, context: RunContext, parent: BaseRunner | None = None
    ):
        super().__init__(step, context, parent)
        self._model = step

    async def _pre_run(self):
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
        if not bool(eval(str(self._model.run_if))):
            self._status = RunnerStatus.CANCELED
            raise Exception("Step skipped due to run_if condition")

    async def _post_run(self):
        stdout = self._result.outputs.get("stdout", "")
        if stdout and isinstance(stdout, str):
            logger.info(self._produce_log(f"stdout:\n{stdout}"))
            if self.model.log_stdout:
                tmp_file = (
                    self.ctx_vars.output_path
                    / f"stdout_{self.parent.model.jid}_{self.model.name.replace(' ', '-')}__{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                logger.info(
                    self._produce_log(f"Saving output of '{self.parent.model.jid}'[{self.model.step_index}] to {tmp_file}")
                )
                tmp_file.write_text(stdout)
        logger.debug(self._produce_log(f"result: {self._result}"))

    async def _do_run(self):
        if self._run_type is RunType.WORKFLOW:
            from ofx.runner.workflow import WorkflowRunner
            output_path = Path.cwd()
            parent = getattr(self, 'parent', None)
            if parent and getattr(parent, 'parent', None):
                output_path = getattr(parent.parent.ctx_vars, 'output_path', Path.cwd())
            runner = WorkflowRunner(
                WorkflowRunner.find_flow(self._model.uses or ""),
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
            assert self.model.script is not None, (
                "Script cannot be None for SCRIPT run type"
            )
            runner = ScriptRunner(
                self.model.script,
                self.ctx_vars.model_copy(),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
            )
        elif self._run_type is RunType.COMMAND:
            assert self.model.run is not None, "Run cannot be None for COMMAND run type"
            runner = CommandRunner(
                self.model.run,
                self.ctx_vars.model_copy(),
                shell=self.model.shell,
                working_dir=self._resolve_working_dir(),
                parent=self,
                timeout_minutes=self.model.timeout,
            )
        res = await runner.run()
        self._status = res.status
        self._error = res.error
        for k, v in res.model_dump().items():
            setattr(self._result, k, v)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))

    def _produce_log(self, message: Any) -> str:
        msg = str(message)
        step_idx = self._model.step_index if hasattr(self._model, 'step_index') else '?'
        msg = f"'step{step_idx}' › {msg}"
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
        step = self._model
        step_path = Path(step.working_directory)
        if step_path.is_absolute():
            return step_path
        # Try to get job_path from parent
        job_path = Path.cwd()
        parent = getattr(self, 'parent', None)
        if parent and hasattr(parent, 'model'):
            job_model = getattr(parent, 'model', None)
            job_defaults = getattr(job_model, 'defaults', None)
            if job_defaults and hasattr(job_defaults, 'run'):
                job_path = Path(getattr(job_defaults.run, 'working_directory', Path.cwd()))
        if job_path.is_absolute():
            return job_path / step_path
        # Try to get workflow_path from parent's parent
        workflow_path = Path.cwd()
        if parent and getattr(parent, 'parent', None):
            workflow_parent = parent.parent
            if hasattr(workflow_parent, 'model'):
                wf_model = getattr(workflow_parent, 'model', None)
                wf_defaults = getattr(wf_model, 'defaults', None)
                if wf_defaults and hasattr(wf_defaults, 'run'):
                    workflow_path = Path(getattr(wf_defaults.run, 'working_directory', Path.cwd()))
        return workflow_path / job_path / step_path

    @property
    def model(self) -> Step:
        return self._model
