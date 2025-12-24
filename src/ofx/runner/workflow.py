"""Workflow runner for parallel job execution and workflow orchestration"""

import asyncio
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Optional

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
from ofx.runner.command import CommandRunner
from ofx.runner.job import JobRunner
from ofx.runner.models import RunContext, RunnerStatus
from ofx.settings import settings, DEFAULT_WORKFLOWS_DIR, TOOLS_DIR, TOOLS_BIN_DIR
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
        self._job_registry: Dict[str, Any] = {}
        self._job_threads: Dict[str, threading.Thread] = {}
        self._job_results: Dict[str, bool] = {}
        self._job_errors: Dict[str, Exception] = {}

    async def _do_run(self):
        """Execute the workflow by running its jobs in stages according to their dependencies"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=self._is_reused or not self.is_finished,
        ) as progress:
            total_steps = self._planning_jobs()
            progress_id = progress.add_task(
                description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{self.model.name}[/bold]'",
                total=total_steps,
            )
            for idx, stage in enumerate(self._schedule):
                logger.debug(self._produce_log(f"Running stage {idx + 1}: {stage}"))

                for job_id in stage:
                    thread = threading.Thread(
                        target=self._run_job_wrapper,
                        args=(job_id,),
                        name=f"job-{job_id}",
                        daemon=False,
                    )
                    self._job_threads[job_id] = thread
                    thread.start()

                while any(self._job_threads[jid].is_alive() for jid in stage):
                    current_steps_completed = sum(
                        self._job_registry[jid]["runner"].processed_steps
                        for jid in stage
                        if jid in self._job_registry
                        and "runner" in self._job_registry[jid]
                    )
                    self._completed_steps = max(
                        self._completed_steps, current_steps_completed
                    )
                    progress.update(
                        progress_id,
                        description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{self.model.name}[/bold]' - Stage {idx + 1}/{len(self._schedule)}",
                        completed=min(self._completed_steps, total_steps),
                        refresh=True,
                    )
                    await asyncio.sleep(0.05)

                for job_id in stage:
                    self._job_threads[job_id].join()

                for job_id in stage:
                    if job_id in self._job_errors:
                        raise RuntimeError(
                            self._produce_log(
                                f"Failed when running job '{job_id}': {self._job_errors[job_id]}"
                            )
                        )
                    if not self._job_results.get(job_id, False):
                        raise RuntimeError(self._produce_log(f"Job '{job_id}' failed"))
                    logger.debug(self._produce_log(f"Job '{job_id}' completed"))

            progress.update(
                progress_id,
                description=f"{'Sub-w' if self._is_reused else 'W'}orkflow '[bold]{self.model.name}[/bold]' completed",
                completed=total_steps,
                refresh=True,
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

    def _run_job_wrapper(self, job_id: str):
        """Wrapper for _run_job to capture results and errors in thread context"""
        try:
            result = self._run_job(job_id)
            self._job_results[job_id] = result
        except Exception as e:
            self._job_errors[job_id] = e
            self._job_results[job_id] = False

    def _run_job(self, job_id: str) -> bool:
        """Set up and run a job with the given job_id"""
        job = self.model.jobs[job_id]
        logger.debug(self._produce_log(f"starting job: {job}"))
        self._job_registry[job_id] = self._resolve_template(
            job.model_dump(exclude={"outputs", "steps"})
        )
        self._ctx.vars.update({"jobs": self._job_registry})
        job_runner = JobRunner(
            job,
            self.ctx_vars,
            parent=self,
        )
        self._job_registry[job_id]["runner"] = job_runner
        try:
            self._run_and_monitor_job(job)
            job_result = job_runner.get_result()
            self._job_registry[job_id].update(job_result.model_dump())
            self._job_registry[job_id]["steps"] = {}
            self._job_registry[job_id]["steps"].update(
                job_result.outputs.get("steps", {})
            )
            self._ctx.vars.update({"jobs": self._job_registry})
            logger.info(self._produce_log(f"done: {job}"))
            return True
        except Exception as e:
            logger.error(job_runner._produce_log(f"Job execution failed: {e}"))
            return False

    def _run_and_monitor_job(self, job):
        """Run a job asynchronously and monitor its progress with a progress bar"""
        job_id = job.jid
        job_runner: JobRunner = self._job_registry[job_id]["runner"]
        if not job_runner:
            raise ValueError(f"Job with ID '{job_id}' not found.")
        job_name = job.name or job_id
        total_steps = job_runner.total_steps

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as job_progress:
            running_msg = f"Running job '[bold]{job_name}[/bold]'"
            progress_task_id = job_progress.add_task(
                description=running_msg,
                total=total_steps,
            )

            job_result: list[Optional[Any]] = [None]
            job_error: list[Optional[Exception]] = [None]

            def run_job_thread():
                try:
                    job_result[0] = asyncio.run(job_runner.run())
                except Exception as e:
                    job_error[0] = e

            job_thread = threading.Thread(
                target=run_job_thread, name=f"monitor-{job_id}", daemon=False
            )
            job_thread.start()

            while job_thread.is_alive():
                job_progress.update(
                    progress_task_id,
                    completed=job_runner.processed_steps,
                    description=running_msg,
                    refresh=True,
                )
                asyncio.run(asyncio.sleep(0.05))

            job_thread.join()

            if job_error[0]:
                raise job_error[0]

    async def _pre_run(self):
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
        self._model.defaults.workflows_base_dir = Path(
            self._resolve_template(self.model.defaults.workflows_base_dir)
        )
        WorkflowRunner.add_workflow_dir(
            self._model.defaults.workflows_base_dir.absolute()
        )

        self._resolve_template_fields(
            ["name", "tools", "env", "description", "tags", "schedule"]
        )
        for job_id, job in self.model.jobs.items():
            self._model.jobs[job_id].name = self._resolve_template(job.name)

        logger.debug(self._produce_log(f"Resolved workflow: {self.model.model_dump()}"))

        self._ctx.envs.update(self.model.env)
        logger.debug(self._produce_log(f"Processed context: {self.ctx_vars}"))
        await self._install_tools()

    async def _post_run(self):
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
                k: self._resolve_template(v)
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
                    [
                        job["status"] == RunnerStatus.COMPLETED
                        for job in self._job_registry.values()
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
            for job_id, thread in self._job_threads.items():
                if thread.is_alive():
                    logger.warning(
                        self._produce_log(
                            f"Thread for job '{job_id}' still running, waiting..."
                        )
                    )
                    thread.join(timeout=5.0)

    async def _install_tools(self):
        tools = self.model.tools
        if not tools:
            return
        
        # Ensure tools directories exist
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        TOOLS_BIN_DIR.mkdir(parents=True, exist_ok=True)
        
        # Add tools bin directory to PATH for this workflow
        workflow_envs = self.ctx_vars.envs.copy()
        current_path = workflow_envs.get("PATH", os.environ.get("PATH", ""))
        if str(TOOLS_BIN_DIR) not in current_path:
            workflow_envs["PATH"] = f"{TOOLS_BIN_DIR}:{current_path}"
            self._ctx.envs.update(workflow_envs)
        
        for tool_bin, install_cmd in tools.items():
            # Check if tool exists in tools_bin_dir or system PATH
            tool_path = TOOLS_BIN_DIR / tool_bin
            if not (tool_path.exists() or shutil.which(tool_bin)):
                logger.warning(
                    self._produce_log(
                        f"Installing tool '{tool_bin}' with command: {install_cmd}"
                    )
                )
                runner = CommandRunner(
                    install_cmd,
                    RunContext(
                        envs=workflow_envs,
                    ),
                )
                _ = await runner.run()
                assert runner.is_success, f"Failed to install tool '{tool_bin}'"
                logger.info(
                    self._produce_log(f"Tool '{tool_bin}' installed to {TOOLS_DIR}")
                )
            else:
                logger.debug(
                    self._produce_log(f"Tool '{tool_bin}' is already installed")
                )

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
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
            req_inputs[key] = self._resolve_template(value)

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
        msg = f"({'sub-' if self._is_reused else ''}workflow '{self.model.name}')[{self._status.value.upper()}] -> {message_str}"
        if self.parent:
            return self.parent._produce_log(msg)
        return msg

    def get_output_path(self) -> Path:
        """Get output path"""
        return self.ctx_vars.output_path

    @staticmethod
    def add_workflow_dir(path: Path | str):
        if path not in WorkflowRunner.flows_dirs:
            WorkflowRunner.flows_dirs.append(Path(path).absolute())

    @staticmethod
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
                )

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
                    raise RuntimeError(f"Failed to load workflow from {path}: {e}")

        if is_remote_path(workflow_name):
            try:
                response = httpx.get(workflow_name)
                response.raise_for_status()
                return Workflow.model_validate(yaml.safe_load(response.text.strip()))
            except Exception as e:
                logger.error(f"Failed to fetch workflow from {workflow_name}: {e}")
                raise RuntimeError(
                    f"Failed to fetch workflow from {workflow_name}: {e}"
                )

        git_path = clone_remote_repo(workflow_name)
        if not git_path:
            raise RuntimeError(f"Workflow {workflow_name} not found.")

        WorkflowRunner.add_workflow_dir(git_path.absolute())
        try:
            return Workflow.model_validate(
                yaml.safe_load((git_path / "main.yml").read_text().strip())
            )
        except Exception as e:
            logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to load workflow from git repo {workflow_name}: {e}"
            )

    def get_job_status(self, job_id: str) -> RunnerStatus:
        return self._job_registry.get(job_id, {}).get("status")

    def get_job_from_registry(
        self, job_id: str
    ) -> Dict[str, JobRunner | Dict[str, Any]] | None:
        return self._job_registry.get(job_id)

    @property
    def model(self) -> Workflow:
        return self._model
