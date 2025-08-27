import logging
import time

from ofx.runner.base import BaseRunner, RunnerStatus, RunContext
from ofx.runner.step import StepRunner
from ofx.models.job import Job
from ofx.settings import settings

from typing import Any

logger = logging.getLogger(settings.app_branding)


class JobRunner(BaseRunner):
    def __init__(self, job: Job, ctx: RunContext, parent: BaseRunner | None = None):
        super().__init__(job, ctx, parent)
        self._model = job
        self._step_registry = {}
        self._processed_steps = 0

    async def _do_run(self):
        for step in self.model.steps:
            step_runner = StepRunner(
                step,
                RunContext(
                    inputs={
                        **self.ctx_vars.inputs,
                        **self._resolve_template(step.run_with),
                    },
                    envs={**self.ctx_vars.envs, **self._resolve_template(step.env)},
                    output_path=self.ctx_vars.output_path,
                    secrets={
                        **self.ctx_vars.secrets,
                        **self._resolve_template(
                            step.secrets if step.secrets != "inherit" else {}
                        ),
                    },
                    vars=self.ctx_vars.vars,
                ),
                self,
            )
            start_time = time.time()
            result = await step_runner.run()
            result.metadata.update({"duration": int(time.time() - start_time)})
            step_name = step.name
            step_id = step.step_index
            dump_model = result.model_dump()
            self._step_registry[step_id] = dump_model
            if step.id:
                self._step_registry[step.id] = dump_model
            self._processed_steps += 1
            if not step_runner.is_success and not step.continue_on_error:
                self._status = RunnerStatus.FAILED
                self._error = result.error
                raise RuntimeError(
                    self._produce_log(
                        f"(step '{step_name}') -> job execution stopped due to step failure: {self._error}"
                    )
                )

    async def _pre_run(self):
        self._resolve_template_fields(["name", "needs", "run_if", "env"])
        for idx, step in enumerate(self._model.steps):
            self._model.steps[idx].name = self._resolve_template(step.name)
            self._model.steps[idx].id = self._resolve_template(step.id)
        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Resolved job: {self.model.model_dump()}"))
        if self.model.needs:
            unmet_deps = []
            for job_id in self.model.needs:
                try:
                    if self.parent.get_job_status(job_id) != RunnerStatus.COMPLETED:
                        unmet_deps.append(job_id)
                except Exception as e:
                    logger.error(
                        self._produce_log(
                            f"Error checking dependency status for {job_id}: {e}"
                        )
                    )
                    unmet_deps.append(job_id)

            if len(unmet_deps) > 0:
                raise RuntimeError(
                    f"Job cannot run because dependencies are not met: {unmet_deps}"
                )

        if not eval(str(self._model.run_if)):
            raise RuntimeError(self._produce_log(f"Job condition is not met"))
        self._ctx.vars.update(
            {
                "steps": self._step_registry,
                "needs": {
                    jid: self.parent.get_job_from_registry(jid)
                    for jid in self.model.needs
                },
            }
        )

    async def _post_run(self):
        """
        Perform post-run tasks and prepare the final result.

        This method collects job execution results and prepares the final output
        for retrieval by the workflow manager.
        """
        if self.status != RunnerStatus.COMPLETED or self._error:
            logger.error(self._produce_log(f"job failed: {self._error}"))
        self._ctx.vars.update({"steps": self._step_registry})
        self._result.outputs.update({"steps": self._step_registry})
        if self.model.outputs:
            for key, value in self.model.outputs.items():
                self._result.outputs[key] = self._resolve_template(value)
        logger.debug(
            self._produce_log(f"job '{self._model.name}' result: {self._result}")
        )

    def _produce_log(self, message: Any) -> str:
        """
        Format a log message with job context information.

        Args:
            message: The message to format

        Returns:
            str: Formatted log message with job context
        """
        job_name = self._model.name
        job_id = self._model.jid
        status = self._status.value.upper()

        message_str = str(message)
        msg = f"(job '{job_id}' - '{job_name}')[{status}] -> {message_str}"

        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def processed_steps(self) -> int:
        """
        Get the number of processed steps.

        Returns:
            int: The number of steps that have been processed
        """
        return self._processed_steps

    @property
    def total_steps(self) -> int:
        """
        Get the total number of steps in the job.

        Returns:
            int: The total number of steps
        """
        return len(self.model.steps)

    @property
    def model(self) -> Job:
        return self._model
