"""Workflow runner for parallel job execution and workflow orchestration"""

import asyncio
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from ofx.models.workflow import Workflow
from ofx.runner.base import BaseRunner
from ofx.runner.job import JobRunner
from ofx.runner.models import RunContext, RunnerStatus
from ofx.runner.tool_installer import ToolInstallerRunner
from ofx.settings import DEFAULT_WORKFLOWS_DIR, settings
from ofx.utils.misc import clone_remote_repo, find_parallel_schedule, is_remote_path

logger = logging.getLogger(settings.app_branding)


class WorkflowRunner(BaseRunner):
    flows_dirs = [DEFAULT_WORKFLOWS_DIR.absolute(), Path.cwd().absolute()]

    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(workflow, ctx, parent)
        self._model = workflow
        self._is_reused = self._parent is not None
        self._job_registry: dict[str, Any] = {}
        self._job_results: dict[str, bool] = {}
        self._job_errors: dict[str, Exception] = {}
        self._progress: Progress | None = None
        self._progress_id: Any | None = None

    async def _do_run(self) -> None:
        """Execute the workflow by running its jobs in stages according to their dependencies"""
        has_interactive = self._has_interactive_steps()

        if not self._is_reused and not has_interactive:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                transient=False,
            )

        try:
            if self._progress:
                self._progress.start()
                workflow_prefix = "⚙"
                total_steps = self._planning_jobs()
                self._progress_id = self._progress.add_task(
                    description=f"{workflow_prefix} [bold]{self.model.name}[/bold]",
                    total=total_steps,
                )
            else:
                self._planning_jobs()

            await self._execute_workflow()

            if self._progress and self._progress_id is not None:
                self._progress.update(
                    self._progress_id,
                    description=f"✓ [bold]{self.model.name}[/bold]",
                    completed=self._total_steps,
                    refresh=True,
                )
        finally:
            if self._progress:
                self._progress.stop()

    async def _execute_workflow(self) -> None:
        """Execute workflow jobs in stages"""
        semaphore = asyncio.Semaphore(settings.workers)

        completed_steps_before_stage = 0
        for idx, stage in enumerate(self._schedule):
            logger.debug(self._produce_log(f"Running stage {idx + 1}: {stage}"))

            job_runners = {}
            for job_id in stage:
                job = self.model.jobs[job_id]
                self._job_registry[job_id] = await self._resolve_template(
                    job.model_dump(exclude={"outputs", "steps"})
                )
                self._ctx.vars.update({"jobs": self._job_registry})
                is_single_job_stage = len(stage) == 1
                job_ctx = self.ctx_vars.model_copy(
                    update={"allow_interactive": is_single_job_stage}
                )

                runner = JobRunner(job, job_ctx, parent=self)
                job_runners[job_id] = runner
                self._job_registry[job_id]["runner"] = runner

            async def run_job_with_limit(job_id: str, runner: JobRunner):
                async with semaphore:
                    return await self._run_and_monitor_job(job_id, runner)

            stage_tasks = {
                job_id: asyncio.create_task(run_job_with_limit(job_id, runner))
                for job_id, runner in job_runners.items()
            }

            if self._progress and self._progress_id is not None:
                while not all(task.done() for task in stage_tasks.values()):
                    current_steps_in_stage = sum(
                        runner.processed_steps for runner in job_runners.values()
                    )
                    self._completed_steps = (
                        completed_steps_before_stage + current_steps_in_stage
                    )

                    self._progress.update(
                        self._progress_id,
                        description=f"⚙ [bold]{self.model.name}[/bold] → {', '.join(stage)}",
                        completed=min(self._completed_steps, self._total_steps),
                        refresh=True,
                    )
                    await asyncio.sleep(0.1)

            results = await asyncio.gather(*stage_tasks.values(), return_exceptions=True)

            stage_failed = False
            failed_jobs_info = []

            stage_steps = 0
            for job_id, result in zip(stage_tasks.keys(), results, strict=False):
                runner = job_runners[job_id]
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

            self._ctx.vars.update({"jobs": self._job_registry})

            completed_steps_before_stage += stage_steps

            if stage_failed:
                error_summary = ", ".join(failed_jobs_info)
                raise RuntimeError(
                    f"One or more jobs failed in stage {idx + 1}: {error_summary}"
                )

    def _planning_jobs(self) -> int:
        """Plan the job execution by organizing them in stages based on dependencies"""
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
        self._schedule = find_parallel_schedule(job_keys, deps_relationships)

        self._total_steps = sum(
            sum(len(jobs[job_id].steps) for job_id in stage) for stage in self._schedule
        )
        logger.debug(self._produce_log(f"Execution stages: {self._schedule}"))
        self._completed_steps = 0
        return self._total_steps

    async def _run_and_monitor_job(self, job_id: str, job_runner: JobRunner):
        """Run a job asynchronously and monitor its progress with a progress bar"""
        total_steps = job_runner.total_steps
        has_interactive_step = any(getattr(step, 'interactive', False) for step in job_runner.model.steps)

        if has_interactive_step and job_runner.ctx_vars.allow_interactive:
            logger.info(self._produce_log(f"Running job '{job_id}' with interactive steps (progress hidden)"))
            return await job_runner.run()

        indicator = "  ↳ " if self._is_reused else "→ "
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as job_progress:
            task_id = job_progress.add_task(f"{indicator}[bold]{job_id}[/bold]", total=total_steps)

            run_task = asyncio.create_task(job_runner.run())

            while not run_task.done():
                processed = job_runner.processed_steps
                step_name = ""
                if processed < len(job_runner.model.steps):
                    current_step = job_runner.model.steps[processed]
                    step_name = f" → {current_step.name or current_step.uses or f'step {processed + 1}'}"

                job_progress.update(
                    task_id,
                    completed=processed,
                    description=f"{indicator}[bold]{job_id}[/bold]{step_name}",
                    refresh=True,
                )
                await asyncio.sleep(0.1)

            job_progress.update(task_id, completed=job_runner.processed_steps, description=f"{indicator}[bold]{job_id}[/bold] ✓", refresh=True)

            return await run_task

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
            self._ctx.inputs.update(
                await self._process_inputs(
                    self._ctx.inputs, self.model.workflow_dispatch.inputs
                )
            )
        if self.model.workflow_call and self._is_reused:
            self._ctx.inputs.update(
                await self._process_inputs(self._ctx.inputs, self.model.workflow_call.inputs)
            )
            self._ctx.secrets.update(
                await self._process_inputs(
                    self._ctx.secrets, self.model.workflow_call.secrets
                )
            )
        self._model.defaults.workflows_base_dir = Path(
            await self._resolve_template(self.model.defaults.workflows_base_dir)
        )
        WorkflowRunner.add_workflow_dir(
            self._model.defaults.workflows_base_dir.absolute()
        )

        await self._resolve_template_fields(
            ["name", "tools", "env", "description", "tags", "schedule"]
        )
        for job_id, job in self.model.jobs.items():
            self._model.jobs[job_id].name = await self._resolve_template(job.name)

        logger.debug(self._produce_log(f"Resolved workflow: {self.model.model_dump()}"))

        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Processed context: {self.ctx_vars}"))
        await self._install_tools()

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
        """Install workflow tools using ToolInstallerRunner"""
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

        self._ctx.envs.update(installer.ctx_vars.envs)

    async def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> dict[str, Any]:
        """Process and validate inputs against the workflow's input constraints"""
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
        """Validate that a value matches the expected type"""
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
        """Get output path"""
        return self.ctx_vars.output_path

    @staticmethod
    def add_workflow_dir(path: Path | str):
        if path not in WorkflowRunner.flows_dirs:
            WorkflowRunner.flows_dirs.append(Path(path).absolute())

    @staticmethod
    @lru_cache(maxsize=32)
    def find_flow(workflow_name: str) -> Workflow:
        """Find and load a workflow from local directories, file path, URL, or git repository"""
        logger.debug(
            f"Searching for workflow: {workflow_name} in {WorkflowRunner.flows_dirs}"
        )

        if Path(workflow_name).exists():
            try:
                flow = Workflow.model_validate(
                    yaml.safe_load(Path(workflow_name).read_text().strip())
                )
                WorkflowRunner.add_workflow_dir(Path(workflow_name).parent.absolute())
                return flow
            except Exception as e:
                logger.error(f"Failed to load workflow from file {workflow_name}: {e}")
                raise RuntimeError(
                    f"Failed to load workflow from file {workflow_name}: {e}"
                ) from e

        for directory in WorkflowRunner.flows_dirs:
            path = directory / f"{workflow_name.rstrip('.yml')}.yml"
            if path.exists():
                try:
                    if path.parent.exists():
                        WorkflowRunner.add_workflow_dir(path.parent.absolute())
                    return Workflow.model_validate(
                        yaml.safe_load(path.read_text().strip())
                    )
                except Exception as e:
                    logger.error(f"Failed to load workflow from {path}: {e}")
                    raise RuntimeError(f"Failed to load workflow from {path}: {e}") from e

        if is_remote_path(workflow_name):
            try:
                response = httpx.get(workflow_name)
                response.raise_for_status()
                return Workflow.model_validate(yaml.safe_load(response.text.strip()))
            except Exception as e:
                logger.error(f"Failed to fetch workflow from {workflow_name}: {e}")
                raise RuntimeError(
                    f"Failed to fetch workflow from {workflow_name}: {e}"
                ) from e

        git_path = clone_remote_repo(workflow_name)
        if not git_path:
            raise RuntimeError(f"Workflow {workflow_name} not found.") from None

        WorkflowRunner.add_workflow_dir(git_path.absolute())
        try:
            return Workflow.model_validate(
                yaml.safe_load((git_path / "main.yml").read_text().strip())
            )
        except Exception as e:
            logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to load workflow from git repo {workflow_name}: {e}"
            ) from e

    def get_job_status(self, job_id: str) -> RunnerStatus:
        return self._job_registry.get(job_id, {}).get("status")

    def get_job_from_registry(
        self, job_id: str
    ) -> dict[str, JobRunner | dict[str, Any]] | None:
        return self._job_registry.get(job_id)

    def _has_interactive_steps(self) -> bool:
        """Check if workflow contains any interactive steps in single-job stages"""
        for job in self.model.jobs.values():
            if any(getattr(step, 'interactive', False) for step in job.steps):
                return True
        return False

    def _stage_has_interactive(self, stage: set[str]) -> bool:
        """Check if a stage has interactive steps (only in single-job stages)"""
        if len(stage) != 1:
            return False
        job_id = list(stage)[0]
        job = self.model.jobs[job_id]
        return any(getattr(step, 'interactive', False) for step in job.steps)

    @property
    def model(self) -> Workflow:
        return self._model
