"""Job runner for orchestrating step execution"""

import logging
import time
from typing import Any

from ofx.models.job import Job
from ofx.runner.core import BaseRunner, RunContext, RunnerStatus
from ofx.runner.step import StepRunner
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class JobRunner(BaseRunner):
    def __init__(self, job: Job, ctx: RunContext, parent: BaseRunner | None = None):
        super().__init__(job, ctx, parent)
        self._model = job
        self._step_registry: list[dict[str, Any]] = [{} for _ in job.steps]
        self._processed_steps = 0

    async def _do_run(self) -> None:
        for step in self.model.steps:
            resolved_inputs = await self._resolve_template(step.run_with)
            resolved_envs = await self._resolve_template(step.env)
            resolved_secrets = (
                await self._resolve_template(step.secrets)
                if step.secrets != "inherit"
                else {}
            )

            step_ctx = self.ctx_vars.model_copy(
                update={
                    "inputs": self.ctx_vars.inputs | resolved_inputs,
                    "envs": self.ctx_vars.envs | resolved_envs,
                    "secrets": self.ctx_vars.secrets | resolved_secrets,
                },
                deep=True,
            )

            step_runner = StepRunner(
                step,
                step_ctx,
                self,
            )
            start_time = time.time()
            result = await step_runner.run()
            result.metadata.update({"duration": int(time.time() - start_time)})
            step_id = step.step_index
            dump_model = result.model_dump()
            self._step_registry[step_id] = dump_model
            self._processed_steps += 1
            if not step_runner.is_success and not step.continue_on_error:
                self._status = RunnerStatus.FAILED
                self._error = result.error
                break

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(["name", "needs", "run_if", "env"])
        for idx, step in enumerate(self._model.steps):
            self._model.steps[idx].name = await self._resolve_template(step.name)
            self._model.steps[idx].id = await self._resolve_template(step.id)
        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Resolved job: {self.model.model_dump()}"))
        if self.model.needs:
            unmet_deps = []
            for job_id in self.model.needs:
                try:
                    if (
                        self.parent
                        and hasattr(self.parent, "get_job_status")
                        and self.parent.get_job_status(job_id) != RunnerStatus.COMPLETED
                    ):
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
        if not self._model.run_if:
            raise RuntimeError(self._produce_log("Job condition is not met"))
        needs_data = {}
        if (
            self.model.needs
            and self.parent
            and hasattr(self.parent, "get_job_from_registry")
        ):
            needs_data = {
                jid: self.parent.get_job_from_registry(jid) for jid in self.model.needs
            }
        self._ctx.vars.update(
            {
                "steps": self._step_registry,
                "needs": needs_data,
                "jobs": self.parent.ctx_vars.vars.get("jobs", {})
                if self.parent
                else {},
            }
        )

    async def _post_run(self) -> None:
        self._ctx.vars.update({"steps": self._step_registry})
        self._result.outputs.update({"steps": self._step_registry})
        if self.model.outputs:
            for key, value in self.model.outputs.items():
                self._result.outputs[key] = await self._resolve_template(value)
        logger.debug(
            self._produce_log(
                f"job '{self.model.name or self.model.jid}' result: {self._result}"
            )
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        msg = f"'{self._model.jid}' › {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    @property
    def processed_steps(self) -> int:
        return self._processed_steps

    @property
    def total_steps(self) -> int:
        return len(self.model.steps)

    @property
    def model(self) -> Job:
        return self._model
