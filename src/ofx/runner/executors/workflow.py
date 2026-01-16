"""Workflow runner for parallel job execution and workflow orchestration"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from ofx.models.workflow import Workflow
from ofx.runner.core import BaseRunner, RunContext, RunnerStatus
from ofx.runner.executors.job import JobRunner
from ofx.runner.executors.tool_installer import ToolInstallerRunner
from ofx.runner.matrix import MatrixExpander
from ofx.settings import DEFAULT_WORKFLOWS_DIRS, settings
from ofx.utils.misc import add_workflow_dir, find_parallel_schedule

logger = logging.getLogger(settings.app_branding)


class WorkflowRunner(BaseRunner[Workflow]):
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(workflow, ctx, parent)
        self._is_reused = self.parent is not None
        self._job_registry: dict[str, Any] = {}
        self._job_results: dict[str, bool] = {}
        self._job_errors: dict[str, Exception] = {}
        self._expanded_jobs: dict[str, Any] = {}
        self._matrix_semaphores: dict[str, asyncio.Semaphore] = {}

        if not self.ctx_vars.workflow_dirs:
            self.ctx_vars.workflow_dirs = DEFAULT_WORKFLOWS_DIRS

        if not self.model:
            raise ValueError("Workflow model cannot be None")

    async def _do_run(self) -> None:
        """Execute the workflow by running its jobs in stages according to their dependencies"""
        await self._planning_jobs()
        await self._execute_workflow()

    async def _execute_workflow(self) -> None:
        """Execute workflow jobs in stages"""
        semaphore = asyncio.Semaphore(settings.workers)

        completed_steps_before_stage = 0
        for idx, stage in enumerate(self._schedule):
            logger.debug(self._produce_log(f"Running stage {idx + 1}: {stage}"))

            job_runners = {}
            for job_id in stage:
                job_data = self._expanded_jobs[job_id]
                job = job_data["job"]
                matrix_values = job_data["matrix"]
                original_job_id = job_data["original_job_id"]

                resolved_job_dict = await self._resolve_template_with_matrix(
                    job.model_dump(exclude={"outputs", "steps"}), matrix_values
                )
                self._job_registry[job_id] = resolved_job_dict
                self.ctx_vars.vars.update({"jobs": self._job_registry})

                job_ctx = self.ctx_vars.model_copy(
                    update={"allow_interactive": len(stage) == 1},
                    deep=True,
                )
                job_ctx.vars["matrix"] = matrix_values

                runner = JobRunner(job, job_ctx, parent=self)
                job_runners[job_id] = (runner, original_job_id)
                resolved_job_dict["runner"] = runner

            async def run_job_with_limit(
                job_id: str, runner: JobRunner, orig_job_id: str
            ):
                if orig_job_id in self._matrix_semaphores:
                    async with self._matrix_semaphores[orig_job_id]:
                        async with semaphore:
                            return await self._run_and_monitor_job(job_id, runner)
                else:
                    async with semaphore:
                        return await self._run_and_monitor_job(job_id, runner)

            stage_tasks = {
                job_id: asyncio.create_task(run_job_with_limit(job_id, runner, orig_id))
                for job_id, (runner, orig_id) in job_runners.items()
            }

            results = await asyncio.gather(
                *stage_tasks.values(), return_exceptions=True
            )

            stage_failed = False
            failed_jobs_info = []

            stage_steps = 0
            for job_id, (runner, _), result in zip(
                stage_tasks.keys(), job_runners.values(), results, strict=False
            ):
                stage_steps += runner.total_steps

                job_result = runner.get_result()

                if isinstance(result, Exception):
                    self._job_errors[job_id] = result
                    self._job_results[job_id] = False
                    stage_failed = True
                    failed_jobs_info.append(f"'{job_id}': {result}")
                elif not runner.is_success:
                    error = job_result.error or "Unknown error"
                    self._job_errors[job_id] = RuntimeError(error)
                    self._job_results[job_id] = False
                    stage_failed = True
                    failed_jobs_info.append(f"'{job_id}': {error}")
                else:
                    logger.debug(
                        self._produce_log(f"Job '{job_id}' completed successfully")
                    )

                self._job_registry[job_id].update(job_result.model_dump())
                self._job_registry[job_id]["steps"] = job_result.outputs.get(
                    "steps", {}
                )

            self.ctx_vars.vars.update({"jobs": self._job_registry})

            completed_steps_before_stage += stage_steps

            if stage_failed:
                error_summary = ", ".join(failed_jobs_info)
                raise RuntimeError(
                    f"One or more jobs failed in stage {idx + 1}: {error_summary}"
                )

    def _expand_matrix_jobs(self) -> None:
        """Expand jobs with matrix strategies using MatrixExpander"""
        self._expanded_jobs = MatrixExpander.expand_jobs(self.model.jobs)

        # Set up semaphores for max_parallel constraints
        for job_id, job in self.model.jobs.items():
            if job.strategy and job.strategy.max_parallel:
                self._matrix_semaphores[job_id] = asyncio.Semaphore(
                    job.strategy.max_parallel
                )

    async def _resolve_workflow_templates(self) -> None:
        await self._resolve_template_fields(
            ["name", "tools", "env", "description", "tags", "schedule"]
        )

        for job_id, job_data in self._expanded_jobs.items():
            job = job_data["job"]
            matrix_values = job_data["matrix"]

            if matrix_values:
                processed_matrix = {}
                for key, value in matrix_values.items():
                    resolved_value = await self._resolve_template_with_matrix(
                        value, matrix_values
                    )
                    processed_matrix[key] = MatrixExpander.process_matrix_value(
                        resolved_value
                    )
                job_data["matrix"] = processed_matrix
                matrix_values = processed_matrix

            if job.name:
                if matrix_values:
                    job.name = await self._resolve_template_with_matrix(
                        job.name, matrix_values
                    )
                else:
                    job.name = await self._resolve_template(job.name)

        self.ctx_vars.envs.update(self.model.env)
        await self._install_tools()
        logger.debug(self._produce_log(f"Resolved workflow: {self.model.model_dump()}"))

    async def _resolve_template_with_matrix(
        self, value: Any, matrix_values: dict[str, Any]
    ) -> Any:
        original_matrix = self.ctx_vars.vars.get("matrix")
        self.ctx_vars.vars["matrix"] = matrix_values

        try:
            result = await self._resolve_template(value)
            return result
        finally:
            if original_matrix is not None:
                self.ctx_vars.vars["matrix"] = original_matrix
            elif "matrix" in self.ctx_vars.vars:
                del self.ctx_vars.vars["matrix"]

    async def _planning_jobs(self) -> int:
        jobs = self.model.jobs
        job_keys = list(jobs.keys())
        deps_relationships = []
        for job_id, job in jobs.items():
            if job.needs:
                if isinstance(job.needs, str):
                    job.needs = [job.needs]
                for dep in job.needs:
                    if dep and dep not in job_keys:
                        raise ValueError(
                            f"Job '{job.name}' depends on '{dep}', which is not defined in the workflow."
                        )
                    deps_relationships.append((dep, job_id))

        self._expand_matrix_jobs()

        expanded_job_keys = list(self._expanded_jobs.keys())
        expanded_deps = []
        for dep, job_id in deps_relationships:
            dep_jobs = MatrixExpander.get_expanded_job_ids(self._expanded_jobs, dep)
            dependent_jobs = MatrixExpander.get_expanded_job_ids(
                self._expanded_jobs, job_id
            )
            for dep_expanded in dep_jobs:
                for dependent_expanded in dependent_jobs:
                    expanded_deps.append((dep_expanded, dependent_expanded))

        self._schedule = find_parallel_schedule(expanded_job_keys, expanded_deps)

        await self._resolve_workflow_templates()

        self._total_steps = sum(
            sum(len(self._expanded_jobs[job_id]["job"].steps) for job_id in stage)
            for stage in self._schedule
        )
        logger.debug(self._produce_log(f"Execution stages: {self._schedule}"))
        self._completed_steps = 0
        return self._total_steps

    def _get_expanded_job_ids(self, original_job_id: str) -> list[str]:
        """Get all expanded job IDs for an original job (delegates to MatrixExpander)

        Args:
            original_job_id: Original job ID before expansion

        Returns:
            List of expanded job IDs
        """
        return MatrixExpander.get_expanded_job_ids(self._expanded_jobs, original_job_id)

    async def _run_and_monitor_job(self, job_id: str, job_runner: JobRunner):
        has_interactive_step = any(
            getattr(step, "interactive", False) for step in job_runner.model.steps
        )

        if has_interactive_step and job_runner.ctx_vars.allow_interactive:
            logger.info(
                self._produce_log(f"Running job '{job_id}' with interactive steps")
            )

        return await job_runner.run()

    async def _pre_run(self) -> None:
        if not self.ctx_vars.output_path.exists():
            self.ctx_vars.output_path.mkdir(parents=True, exist_ok=True)
        if self.model.defaults:
            os.chdir(self.model.defaults.run.working_directory)
        logger.debug(
            self._produce_log(f"Workflow Dispatch: {self.model.workflow_dispatch}")
        )
        logger.debug(self._produce_log(f"Workflow Call: {self.model.workflow_call}"))
        if self.model.workflow_dispatch and not self._is_reused:
            self.ctx_vars.inputs.update(
                await self._process_inputs(
                    self.ctx_vars.inputs, self.model.workflow_dispatch.inputs
                )
            )
        if self.model.workflow_call and self._is_reused:
            self.ctx_vars.inputs.update(
                await self._process_inputs(
                    self.ctx_vars.inputs, self.model.workflow_call.inputs
                )
            )
            self.ctx_vars.secrets.update(
                await self._process_inputs(
                    self.ctx_vars.secrets, self.model.workflow_call.secrets
                )
            )
        self.model.defaults.workflows_base_dir = Path(
            await self._resolve_template(self.model.defaults.workflows_base_dir)
        )
        self.ctx_vars.workflow_dirs = add_workflow_dir(
            self.ctx_vars.workflow_dirs,
            self.model.defaults.workflows_base_dir.absolute(),
        )
        logger.debug(self._produce_log(f"Processed context: {self.ctx_vars}"))

    async def _post_run(self) -> None:
        if self._status != RunnerStatus.COMPLETED and self._error:
            logger.error(self._produce_log(f"error: {self._error}"))
        self._result.outputs.update(self._job_registry)
        if self._is_reused and self.model.workflow_call:
            if not self.is_success:
                raise RuntimeError(
                    self._produce_log(
                        f"Reusable workflow '{self.model.name}' failed. Cannot retrieve outputs."
                    )
                )
            self._result.outputs = {
                k: await self._resolve_template(v)
                for k, v in self.model.workflow_call.outputs.items()
            }
        logger.debug(
            self._produce_log(
                f"job execution status: {[(job['name'], job['status']) for job in self._job_registry.values()]}"
            )
        )
        self._status = (
            self._status
            if not self._is_reused
            else (
                RunnerStatus.COMPLETED
                if all(
                    job["status"] == RunnerStatus.COMPLETED
                    for job in self._job_registry.values()
                )
                else RunnerStatus.FAILED
            )
        )
        if (
            self.ctx_vars.output_path.exists()
            and len(os.listdir(self.ctx_vars.output_path.absolute())) == 0
        ):
            os.rmdir(self.ctx_vars.output_path)
        logger.debug(self._produce_log(f"result: {self.get_result()}"))

    async def _install_tools(self) -> None:
        tools = self.model.tools
        if not tools:
            return

        installer = ToolInstallerRunner(
            tools=tools,
            ctx=RunContext(envs=self.ctx_vars.envs.copy()),
            parent=self,
            show_console=False,
        )
        await installer.run()

        self.ctx_vars.envs.update(installer.ctx_vars.envs)

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

    def get_output_path(self) -> Path:
        return self.ctx_vars.output_path

    def get_job_status(self, job_id: str) -> RunnerStatus:
        if job_id in self._job_registry:
            return self._job_registry.get(job_id, {}).get("status")

        expanded_ids = MatrixExpander.get_expanded_job_ids(self._expanded_jobs, job_id)
        if not expanded_ids or expanded_ids == [job_id]:
            return self._job_registry.get(job_id, {}).get("status")

        statuses = []
        for expanded_id in expanded_ids:
            status = self._job_registry.get(expanded_id, {}).get("status")
            if status:
                statuses.append(status)

        if any(s == RunnerStatus.FAILED for s in statuses):
            return RunnerStatus.FAILED
        if any(s == RunnerStatus.CANCELED for s in statuses):
            return RunnerStatus.CANCELED
        if all(s == RunnerStatus.COMPLETED for s in statuses) and len(statuses) == len(
            expanded_ids
        ):
            return RunnerStatus.COMPLETED
        return RunnerStatus.RUNNING if statuses else RunnerStatus.IDLE

    def get_job_from_registry(
        self, job_id: str
    ) -> dict[str, JobRunner | dict[str, Any]] | None:
        return self._job_registry.get(job_id)

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
