"""Workflow runner for parallel job execution and workflow orchestration"""

import asyncio
import logging
import os
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.models.config import DefaultConfig
from ofx.runner.core import (
    BaseRunner,
    RegistryAdapter,
    RunContext,
    RunnerStatus,
)
from ofx.runner.executors.job import JobRunner, MatrixJobRunner
from ofx.runner.executors.tool_installer import ToolInstallerRunner
from ofx.settings import settings
from ofx.utils.scheduling import find_parallel_schedule
from ofx.utils.workflow_utils import add_workflow_dir

logger = logging.getLogger(settings.app_branding)


class WorkflowRunner(BaseRunner[Workflow]):
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
        registry: RegistryAdapter | None = None,
    ):
        super().__init__(workflow, ctx, parent, registry)
        self._is_reused = self.parent is not None
        if not self._is_reused:
            self.name = f"[RUN-{self.run_id}]:{self.name}"
        self._runners: dict[str, JobRunner | MatrixJobRunner] = {}

    async def _pre_run(self) -> None:
        await self._resolve_template_fields(
            ["name", "description", "tags", "env", "defaults"]
        )
        logger.debug(
            self._produce_log(
                f"Resolved workflow: {self.model.model_dump(exclude={'jobs'})}"
            )
        )

        output_path = self.ctx.output_path
        if output_path and output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
        os.chdir(self.model.defaults.run.working_directory)

        logger.debug(self._produce_log(f"Workflow Dispatch: {self.model.dispatch}"))
        if self.model.dispatch and not self._is_reused:
            self.ctx.inputs.update(
                await self._process_inputs(self.ctx.inputs, self.model.dispatch.inputs)
            )

        logger.debug(self._produce_log(f"Workflow Call: {self.model.call}"))
        if self.model.call and self._is_reused:
            self.ctx.inputs.update(
                await self._process_inputs(self.ctx.inputs, self.model.call.inputs)
            )
            self.ctx.secrets.update(
                await self._process_inputs(self.ctx.secrets, self.model.call.secrets)
            )

        self.ctx.workflow_dirs = add_workflow_dir(
            self.ctx.workflow_dirs,
            self.model.defaults.workflows_base_dir.absolute(),
        )
        logger.debug(self._produce_log(f"Processed context: {self.ctx}"))

        self.ctx.envs.update(self.model.env)
        
        for jid, job in self.model.jobs.items():
            job_default_config = job.defaults.model_dump(exclude_defaults=True)
            workflow_default_config = self.model.defaults.model_dump()
            for key, value in job_default_config.items():
                workflow_default_config[key] = value
            job.defaults = DefaultConfig.model_validate(workflow_default_config)
            self.model.jobs[jid] = job

        await self._install_tools()

    async def _do_run(self) -> None:
        await self._plan_jobs()
        await self._run_workflow()

    async def _post_run(self) -> None:
        # if not self.is_success:
        #     logger.error(self._produce_log(f"error: {self._error}"))
        if self._is_reused:
            job_runners = self._runners.values()
            # if not self.is_success:
            #     raise RuntimeError(
            #         f"Reusable workflow '{self.model.name}' failed. Cannot retrieve outputs."
            #     )
            if  any(runner.is_failed for runner in job_runners):
                raise RuntimeError(
                    f"Reusable workflow '{self.model.name}' has failed jobs. Cannot retrieve outputs."
                )
        if (
            self.ctx.output_path
            and self.ctx.output_path.exists()
            and len(os.listdir(self.ctx.output_path)) == 0
        ):
            os.rmdir(self.ctx.output_path)
        logger.debug(self._produce_log(f"result: {await self.get_result()}"))

    async def _run_workflow(self) -> None:
        for stage_index, stage in enumerate(self._schedule):
            logger.debug(self._produce_log(f"Stage {stage_index + 1}: {stage}"))
            for job_id in stage:
                job = self.model.jobs[job_id]
                job_ctx = self.ctx.model_copy(
                    update={"allow_interactive": len(stage) == 1}, deep=True
                )
                if job.strategy and job.strategy.matrix:
                    runner = MatrixJobRunner(job, job_ctx, parent=self)
                else:
                    runner = JobRunner(job, job_ctx, parent=self)
                self._runners[job_id] = runner
            tasks = {
                job_id: asyncio.create_task(runner.run())
                for job_id, runner in self._runners.items()
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            failed = False
            errors = []
            for job_id, runner, result in zip(
                tasks.keys(), self._runners.values(), results, strict=False
            ):
                job_result = await runner.get_result()
                if isinstance(result, Exception):
                    failed = True
                    errors.append(f"{job_id}: {result}")
                elif not runner.is_success:
                    error = job_result.error or "Unknown error"
                    failed = True
                    errors.append(f"job '{job_id}': {error}")
            if failed:
                error_summary = "====\n".join(errors)
                raise RuntimeError(
                    f"Job failure in stage {stage_index + 1}:\n{error_summary}"
                )

    async def _plan_jobs(self) -> None:
        jobs = self.model.jobs
        dependencies = []
        for job_id, job in jobs.items():
            needs = [job.needs] if isinstance(job.needs, str) else job.needs
            for dep in needs:
                dependencies.append((dep, job_id))
        self._schedule = find_parallel_schedule(
            list(self.model.jobs.keys()), dependencies
        )
        logger.debug(self._produce_log(f"Stages: {self._schedule}"))

    async def _install_tools(self) -> None:
        tools = self.model.tools
        if not tools:
            return

        installer = ToolInstallerRunner(
            tools=tools,
            ctx=RunContext(envs=self.ctx.envs.copy()),
            parent=self,
            show_console=False,
        )
        await installer.run()

    async def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> dict[str, Any]:
        logger.debug(
            self._produce_log(
                f"Processing inputs: {req_inputs} with blueprint: {input_blueprint}"
            )
        )

        for key, contrain in input_blueprint.items():
            if key not in req_inputs and contrain.required:
                raise ValueError(
                    f"Input '{key}' is required but not provided in the inputs."
                )
            if key in req_inputs:
                value = req_inputs[key]
                if not self._check_input_type(value, contrain.type):
                    raise ValueError(
                        f"Input '{key}' has invalid type: {type(value).__name__}. "
                        f"Expected type: {contrain.type}."
                    )
            else:
                req_inputs[key] = contrain.default
        for key, value in req_inputs.items():
            req_inputs[key] = await self._resolve_template(value)

        return req_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        if input_type == "string":
            return isinstance(value, str)
        elif input_type == "number":
            return isinstance(value, (int, float))
        elif input_type == "boolean":
            return isinstance(value, bool)
        elif input_type == "array":
            return isinstance(value, list)
        elif input_type == "object":
            return isinstance(value, dict)

        raise ValueError(
            f"Unsupported input type '{input_type}' for value '{value}'. "
            f"Supported types are: string, number, boolean, array, object."
        )

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        prefix = f"'{self.model.name}'"
        if self.parent:
            return self.parent._produce_log(f"{prefix} › {message_str}")
        return f"{prefix} › {message_str}"

    def _has_interactive_steps(self) -> bool:
        for job in self.model.jobs.values():
            if any(getattr(step, "interactive", False) for step in job.steps):
                return True
        return False

    def _stage_has_interactive(self, stage: set[str]) -> bool:
        if len(stage) != 1:
            return False
        job_id = list(stage)[0]
        job = self.model.jobs[job_id]
        return any(getattr(step, "interactive", False) for step in job.steps)

    @property
    def runners(self) -> dict[str, JobRunner | MatrixJobRunner]:
        """Get the job runners within the workflow"""
        return self._runners
