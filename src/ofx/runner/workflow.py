import asyncio
import logging
import os
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Dict

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.base import BaseRunner, RunContext, RunnerStatus, RunResult
from ofx.runner.job import JobRunner
from ofx.runner.core.scheduler import JobScheduler
from ofx.runner.core.progress import ProgressTracker
from ofx.runner.loaders.workflow_loader import WorkflowLoader
from ofx.runner.registry.job_registry import JobRegistry
from ofx.settings import settings

processor = ThreadPoolExecutor(max_workers=(settings.workers * 2))

logger = logging.getLogger(settings.app_branding)


class WorkflowRunner(BaseRunner):
    """Runner for executing complete workflows with parallel job execution.
    
    Orchestrates job execution according to dependency graph, manages job
    registry, and tracks overall workflow progress.
    
    Attributes:
        _is_reused: Whether this workflow is called from another workflow
        _processor: ThreadPoolExecutor for parallel job execution
        _scheduler: Job scheduler for dependency resolution
        _registry: Job registry for tracking job state and outputs
        _progress_tracker: Progress tracking for UI/logging
        _schedule: Execution schedule (list of job stages)
        _total_steps: Total number of steps across all jobs
        _completed_steps: Number of completed steps
    """
    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        parent: BaseRunner | None = None,
    ):
        super().__init__(workflow, ctx, parent)
        self._model = workflow
        self._is_reused = self._parent is not None
        self._processor = processor
        self._scheduler = JobScheduler(workflow)
        self._registry = JobRegistry()
        self._progress_tracker = ProgressTracker(is_reused=self._is_reused)
        self._schedule = []
        self._total_steps = 0
        self._completed_steps = 0

    async def _do_run(self):
        with self._progress_tracker.create_workflow_progress(
            self.model.name, self._total_steps
        ) as progress:
            for idx, stage in enumerate(self._schedule):
                logger.debug(self._produce_log(f"Running stage {idx + 1}: {stage}"))
                futures = {
                    self._processor.submit(self._run_job, job_id): job_id
                    for job_id in stage
                }
                completed_jobs = set()
                while len(completed_jobs) < len(stage):
                    done, _ = wait(
                        [f for f in futures.keys() if futures[f] not in completed_jobs],
                        timeout=0.1,
                        return_when=FIRST_COMPLETED,
                    )
                    for f in done:
                        job_id = futures[f]
                        if job_id not in completed_jobs:
                            try:
                                result = f.result()
                                if not result:
                                    raise RuntimeError(
                                        f"Failed when polling job '{job_id}'"
                                    )
                                logger.debug(
                                    self._produce_log(f"Job '{job_id}' completed")
                                )
                            except Exception as e:
                                raise RuntimeError(
                                    self._produce_log(
                                        f"Failed when polling job '{job_id}': {e}"
                                    )
                                )
                            finally:
                                completed_jobs.add(job_id)

                    current_steps_completed = sum(
                        self._registry.get_job_runner(jid).processed_steps
                        for jid in stage
                    )
                    self._completed_steps = max(
                        self._completed_steps, current_steps_completed
                    )
                    self._progress_tracker.update_workflow_progress(
                        self.model.name,
                        idx + 1,
                        len(self._schedule),
                        min(self._completed_steps, self._total_steps),
                        self._total_steps,
                    )

            self._progress_tracker.complete_workflow_progress(
                self.model.name, self._total_steps
            )

    def _planning_jobs(self) -> int:
        self._schedule, self._total_steps = self._scheduler.plan_execution()
        self._completed_steps = 0
        return self._total_steps

    def _run_job(self, job_id: str) -> bool:
        job = self.model.jobs[job_id]
        logger.debug(self._produce_log(f"starting job: {job}"))
        job_data = self._resolve_template(
            job.model_dump(exclude={"outputs", "steps"})
        )
        self._registry.register_job(job_id, job_data)
        self._ctx.vars.update({"jobs": self._registry.get_all_jobs()})
        job_runner = JobRunner(
            job,
            self.ctx_vars,
            parent=self,
        )
        self._registry.set_job_runner(job_id, job_runner)
        try:
            self._run_and_monitor_job(job)
            job_result = job_runner.get_result()
            self._registry.update_job(job_id, job_result.model_dump())
            job = self._registry.get_job(job_id)
            if not job:
                raise RuntimeError(f"Job '{job_id}' not found in registry after run.")
            job["steps"] = {}
            job["steps"].update(job_result.outputs.get("steps", {}))
            self._ctx.vars.update({"jobs": self._registry.get_all_jobs()})
            return True
        except Exception as e:
            logger.error(job_runner._produce_log(f"Job execution failed: {e}"))
            return False

    def _run_and_monitor_job(self, job: Job):
        job_id = job.jid
        job_runner = self._registry.get_job_runner(job_id)
        if not job_runner:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        job_name = job.name or job_id
        total_steps = job_runner.total_steps

        self._progress_tracker.run_job_with_progress(
            job_id, job_name, total_steps, job_runner, self._processor
        )

    async def _pre_run(self):
        # Register hooks from model
        self._register_hooks_from_model()
        
        if not self.ctx_vars.output_path.exists():
            self.ctx_vars.output_path.mkdir(parents=True, exist_ok=True)
        
        # Change to workflow working directory
        if self.model.defaults:
            os.chdir(self.model.defaults.run.working_directory)
            workflows_base_dir = Path(
                self._resolve_template(self.model.defaults.workflows_base_dir)
            )
            WorkflowLoader.add_workflow_dir(workflows_base_dir.absolute())
        
        logger.debug(
            self._produce_log(f"Workflow Dispatch: {self.model.workflow_dispatch}")
        )
        logger.debug(self._produce_log(f"Workflow Call: {self.model.workflow_call}"))
        if self.model.workflow_dispatch and not self._is_reused:
            self._ctx.inputs.update(
                self._process_inputs(
                    self._ctx.inputs, self.model.workflow_dispatch.inputs
                )
            )
        if self.model.workflow_call and self._is_reused:
            self._ctx.inputs.update(
                self._process_inputs(self._ctx.inputs, self.model.workflow_call.inputs)
            )
            self._ctx.secrets.update(
                self._process_inputs(
                    self._ctx.secrets, self.model.workflow_call.secrets
                )
            )

        self._resolve_template_fields(
            ["name", "tools", "env", "description", "tags", "schedule"]
        )
        for job_id, job in self.model.jobs.items():
            self._model.jobs[job_id].name = self._resolve_template(job.name)

        logger.debug(self._produce_log(f"Resolved workflow: {self.model.model_dump()}"))

        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Processed context: {self.ctx_vars}"))
        
        # Execute pre_run hooks
        await self._execute_pre_run_hooks()
        
        await self._install_tools()
        self._planning_jobs()

    async def _post_run(self):
        if self._status != RunnerStatus.COMPLETED and self._error:
            logger.error(self._produce_log(f"error: {self._error}"))
        self._result.outputs.update(self._registry.get_all_jobs())
        
        # Execute post_run hooks
        await self._execute_post_run_hooks()
        if self._is_reused and self.model.workflow_call:
            if not self.is_success:
                raise RuntimeError(
                    self._produce_log(
                        f"Reusable workflow '{self.model.name}' failed. Cannot retrieve outputs."
                    )
                )
            self._result.outputs = {
                k: self._resolve_template(v)
                for k, v in self.model.workflow_call.outputs.items()
            }
        logger.debug(
            self._produce_log(
                f"job execution status: {[(job['name'], job['status']) for job in self._registry.get_all_jobs().values()]}"
            )
        )
        self._status = (
            self._status
            if not self._is_reused
            else (
                RunnerStatus.COMPLETED
                if all(
                    [
                        job["status"] == RunnerStatus.COMPLETED
                        for job in self._registry.get_all_jobs().values()
                    ]
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
        if not self._is_reused:
            self._processor.shutdown(wait=True)

    async def _install_tools(self):
        from ofx.runner.executors.command import CommandExecutor

        tools = self.model.tools
        if not tools:
            return
        for tool_bin, install_cmd in tools.items():
            if not shutil.which(tool_bin):
                logger.warning(
                    self._produce_log(
                        f"Installing tool '{tool_bin}' with command: {install_cmd}"
                    )
                )
                executor = CommandExecutor(
                    install_cmd,
                    RunContext(envs=self.ctx_vars.envs),
                    self,
                )
                result = await executor.execute()
                if result.get("exit_code", 0) != 0:
                    raise RuntimeError(f"Failed to install tool '{tool_bin}'")
            else:
                logger.debug(
                    self._produce_log(f"Tool '{tool_bin}' is already installed")
                )

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
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
            req_inputs[key] = self._resolve_template(value)
        
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
        workflow_name = self.model.name
        if self._is_reused:
            if self.parent:
                return self.parent._produce_log(f"[['{workflow_name}']] -> {message}")
        return f"['{workflow_name}'] -> {message}"

    def get_output_path(self) -> Path:
        return self.ctx_vars.output_path

    @staticmethod
    def find_flow(workflow_name: str) -> Workflow:
        return WorkflowLoader.find_flow(workflow_name)

    def get_job_status(self, job_id: str) -> RunnerStatus:
        status =  self._registry.get_job_status(job_id)
        if not status:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        return status
    
    def get_job_from_registry(
        self, job_id: str
    ) -> Dict[str, Any] | None:
        return self._registry.get_job(job_id)

    @property
    def model(self) -> Workflow:
        return self._model
