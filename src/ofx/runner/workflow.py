import os
import asyncio
import time
import logging
import shutil
import subprocess

from ofx.runner.base import BaseRunner, RunnerStatus, RunContext
from ofx.runner.job import JobRunner
from ofx.models.workflow import Workflow
from ofx.settings import SECRETS_DIR, settings
from ofx.utils.misc import (
    load_secrets,
    find_parallel_schedule,
)

from pathlib import Path
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)
from jinja2 import Template
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

processor = ThreadPoolExecutor(max_workers=(settings.workers * 2))


logger = logging.getLogger("ofx")


class WorkflowRunner(BaseRunner):

    def __init__(
        self,
        workflow: Workflow,
        ctx: RunContext,
        output_path: Path = Path.cwd(),
        is_reused: bool = False,
    ):
        super().__init__(workflow.name, ctx)
        self._workflow = workflow
        self._is_reused = is_reused
        self._inputs = ctx.inputs
        self._default_secrets = load_secrets(SECRETS_DIR)
        self._envs = {}
        self._job_status = {}
        self._output_jobs = {}
        self._output_path = output_path
        self._total_steps = 0
        self._completed_steps = 0
        self._do_init()
        if ctx.secrets:
            self._default_secrets.update(ctx.secrets)
        if ctx.envs:
            self._envs.update(ctx.envs)

    def get_job_status(self, job_id: str) -> RunnerStatus:
        return self._job_status.get(job_id).status

    async def _do_run(self):
        """
        Execute the workflow by running its jobs in stages according to their dependencies.

        This method handles:
        1. Planning the execution stages
        2. Running jobs in parallel within each stage
        3. Tracking progress and updating the progress bar
        4. Error handling for job failures

        Raises:
            RuntimeError: If any job fails during execution
        """
        logger.debug(
            self._produce_log(
                f"Starting workflow with inputs: {self._inputs}, "
                f"environment: {self._envs}, output path: {self._output_path}"
            )
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=self._is_reused,
        ) as progress:
            # Initialize progress tracking
            self._planning_jobs()
            task_id = progress.add_task(
                description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{self._workflow.name}[/bold]'",
                total=self._total_steps,
            )
            # Execute jobs stage by stage
            for stage_num, stage in enumerate(self._schedule):
                logger.debug(
                    self._produce_log(f"Running stage {stage_num + 1}: {stage}")
                )

                # Submit all jobs in this stage for parallel execution
                futures = [processor.submit(self._run_job, job_id) for job_id in stage]
                future_to_job_id = {
                    futures[i]: job_id for i, job_id in enumerate(stage)
                }
                completed_jobs = set()

                # Wait for all jobs in this stage to complete
                while len(completed_jobs) < len(stage):
                    # Wait for the next job to complete
                    done, _ = wait(
                        [
                            f
                            for f in futures
                            if future_to_job_id[f] not in completed_jobs
                        ],
                        timeout=0.1,
                        return_when=FIRST_COMPLETED,
                    )

                    # Process completed jobs
                    for future in done:
                        job_id = future_to_job_id[future]
                        if job_id not in completed_jobs:
                            try:
                                result = future.result()
                                if not result:
                                    raise RuntimeError(f"Job '{job_id}' failed")
                                logger.debug(
                                    self._produce_log(f"Job '{job_id}' completed")
                                )
                            except Exception as e:
                                logger.error(
                                    self._produce_log(
                                        f"Job '{job_id}' failed with error: {e}"
                                    )
                                )
                                raise RuntimeError(
                                    self._produce_log(f"Job '{job_id}' failed: {e}")
                                )
                            finally:
                                completed_jobs.add(job_id)

                    # Update progress tracking
                    current_steps_completed = sum(
                        self._job_status[jid].processed_steps for jid in stage
                    )
                    self._completed_steps = max(
                        self._completed_steps, current_steps_completed
                    )

                    # Update progress bar
                    progress.update(
                        task_id,
                        description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{self._workflow.name}[/bold]' - Stage {stage_num + 1}/{len(self._schedule)}",
                        completed=min(self._completed_steps, self._total_steps),
                    )

            # Mark workflow as completed
            progress.update(
                task_id,
                description=f"{'Sub-' if self._is_reused else ''}workflow '[bold]{self._workflow.name}[/bold]' completed",
                completed=self._total_steps,
            )

    def _planning_jobs(self) -> int:
        """
        Plan the job execution by organizing them in stages based on dependencies.

        Returns:
            int: The total number of steps across all jobs

        Raises:
            ValueError: If a job depends on another job that doesn't exist
        """
        # Get all job IDs
        jobs = list(self._workflow.jobs.keys())
        deps = []

        # Process job dependencies
        for job_id, job in self._workflow.jobs.items():
            if job.needs:
                # Normalize needs to always be a list
                if isinstance(job.needs, str):
                    job.needs = [job.needs]

                # Validate and record dependencies
                for dependency in job.needs:
                    if dependency and dependency not in jobs:
                        raise ValueError(
                            f"Job '{job.name}' depends on '{dependency}', which is not defined in the workflow."
                        )
                    deps.append((dependency, job_id))

        # Generate execution schedule using topological sort
        self._schedule = find_parallel_schedule(jobs, deps)

        # Calculate total steps across all jobs
        self._total_steps = sum(
            sum(len(self._workflow.jobs[job_id].steps) for job_id in stage)
            for stage in self._schedule
        )

        logger.debug(self._produce_log(f"Execution stages: {self._schedule}"))
        self._completed_steps = 0

        return self._total_steps

    def _run_job(self, job_id: str) -> bool:
        """
        Set up and run a job with the given job_id.

        Args:
            job_id: The ID of the job to run

        Returns:
            bool: True if job completed successfully, False otherwise
        """
        logger.debug(self._produce_log(f"Running job: {job_id}"))

        # Set up the job runner
        job = self._workflow.jobs[job_id]
        job_runner = JobRunner(
            job_id,
            job,
            ctx=RunContext(
                inputs=self._inputs, envs=self._envs, secrets=self.get_default_secrets()
            ),
        )
        job_runner.attach_manager(self._manager)
        job_runner.attach_context_provider(self)

        self._output_jobs[job_id] = {"steps": job_runner._step_outputs}
        self._job_status[job_id] = job_runner

        try:
            self._run_and_monitor_job(job_id)
            return True
        except Exception as e:
            logger.error(job_runner._produce_log(f"Job execution failed: {e}"))
            return False

    def _run_and_monitor_job(self, job_id: str):
        """
        Run a job asynchronously and monitor its progress with a progress bar.

        Args:
            job_id: The ID of the job to run and monitor

        Returns:
            The result of the job execution

        Raises:
            Any exception raised during job execution
        """
        job_runner = self._job_status[job_id]
        job = job_runner._job
        total_steps = len(job.steps)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            progress_task_id = progress.add_task(
                description=f"Running job '{job.name}'",
                total=total_steps,
            )
            job_task = processor.submit(asyncio.run, job_runner.run())
            try:
                while not job_task.done():
                    progress.update(
                        progress_task_id,
                        completed=job_runner.processed_steps,
                        description=f"Running job '{job.name}'",
                    )
                    time.sleep(0.1)
                progress.update(
                    progress_task_id,
                    completed=total_steps,
                    description=f"Finished job '{job.name}'",
                )
                return job_task.result()
            except Exception as e:
                progress.update(
                    progress_task_id,
                    description=f"Failed job '{job.name}': {str(e)}",
                    completed=total_steps,
                )
                raise RuntimeError(
                    self._produce_log(f"Job '{job.name}' failed when polling: {str(e)}")
                )

    async def _pre_run(self):
        if self._workflow.defaults:
            working_directory = self._workflow.defaults.run.working_directory
            os.chdir(Path(working_directory))
        tools = self._workflow.tools
        if tools:
            for tool_bin, install_cmd in tools.items():
                install_cmd = self._resolve_template(install_cmd)
                if not shutil.which(tool_bin):
                    logger.info(
                        self._produce_log(
                            f"Installing tool '{tool_bin}' with command: {install_cmd}"
                        )
                    )
                    shell = "/bin/bash" if os.name != "nt" else "cmd.exe"
                    try:
                        result = subprocess.run(
                            args=[shell, "-c", install_cmd],
                            executable=shell,
                            env=self._envs,
                            check=True,
                        )
                    except Exception as e:
                        RuntimeError(f"Failed to install tool '{tool_bin}': {e}")
                else:
                    logger.debug(
                        self._produce_log(f"Tool '{tool_bin}' is already installed")
                    )
        for job_id, job in self._workflow.jobs.items():
            self.workflow.jobs[job_id].name = self._resolve_template(job.name)
            self.workflow.jobs[job_id].needs = [
                self._resolve_template(dep) for dep in job.needs
            ]
            for i, step in enumerate(job.steps):
                self.workflow.jobs[job_id].steps[i].name = self._resolve_template(
                    step.name
                )
                self.workflow.jobs[job_id].steps[i].id = self._resolve_template(step.id)

        logger.debug(
            self._produce_log(f"resolved workflow: {self._workflow.model_dump()}")
        )

    async def _post_run(self) -> Dict[str, Any]:
        if self._status == RunnerStatus.FAILED or not self._success:
            logger.error(self._produce_log(f"error: {self._error}"))
        self._status = RunnerStatus.COMPLETED if self._success else RunnerStatus.FAILED
        self._result["outputs"] = self._output_jobs
        if self._is_reused and self._workflow.workflow_call:
            self._result["outputs"] = {}
            for k, v in self._workflow.workflow_call.outputs.items():
                self._result["outputs"][k] = self._resolve_template(
                    v, self._output_jobs
                )
        self._result["workflow"] = self._workflow.model_dump()
        self._result["run_id"] = self._id
        logger.debug(
            self._produce_log(
                f"job execution status: {[(job._job.name, job.status) for job in self._job_status.values()]}"
            )
        )
        self._result["status"] = (
            self._status
            if not self._is_reused
            else (
                RunnerStatus.COMPLETED
                if all(
                    [
                        job.status == RunnerStatus.COMPLETED
                        for job in self._job_status.values()
                    ]
                )
                else RunnerStatus.FAILED
            )
        )
        self._result["inputs"] = self._inputs
        self._result["envs"] = self._envs
        self._result["output_path"] = str(self._output_path)
        if (
            self._output_path.exists()
            and len(os.listdir(self._output_path.absolute())) == 0
        ):
            os.rmdir(self._output_path)
        else:
            logger.info(self._produce_log(f"output dir: {self._output_path}"))
        logger.debug(self._produce_log(f"result: {self._result}"))

    def _do_init(self):
        """
        Initialize the workflow runner by:
        1. Creating the output directory if it doesn't exist
        2. Processing workflow inputs based on dispatch or call type
        3. Setting up environment variables
        """
        # Ensure output directory exists
        if not self._output_path.exists():
            self._output_path.mkdir(parents=True, exist_ok=True)

        # Log workflow input configurations
        logger.debug(
            self._produce_log(
                f"Workflow dispatch inputs: "
                f"{self._workflow.workflow_dispatch.inputs if hasattr(self._workflow, 'workflow_dispatch') else None}"
            )
        )
        logger.debug(
            self._produce_log(
                f"Workflow call inputs: "
                f"{self._workflow.workflow_call.inputs if hasattr(self._workflow, 'workflow_call') else None}"
            )
        )

        # Process workflow dispatch inputs (for top-level workflows)
        if (
            hasattr(self._workflow, "workflow_dispatch")
            and self._workflow.workflow_dispatch
            and not self._is_reused
        ):
            self._inputs.update(
                self._process_inputs(
                    self._inputs, self._workflow.workflow_dispatch.inputs or {}
                )
            )

        # Process workflow call inputs (for sub-workflows)
        if (
            hasattr(self._workflow, "workflow_call")
            and self._workflow.workflow_call
            and self._is_reused
        ):
            # Process regular inputs
            self._inputs.update(
                self._process_inputs(
                    self._inputs, self._workflow.workflow_call.inputs or {}
                )
            )

            # Process secrets if specified
            if (
                hasattr(self._workflow.workflow_call, "secrets")
                and self._workflow.workflow_call.secrets
            ):
                self._default_secrets.update(
                    self._process_inputs(
                        self._default_secrets,
                        self._workflow.workflow_call.secrets or {},
                    )
                )
        for key, value in self._workflow.env.items():
            self._envs[key] = self._resolve_template(value)
        self._workflow.defaults.workflows_base_dir = self._resolve_template(
            self._workflow.defaults.workflows_base_dir
        )
        self._envs = {**os.environ, **self._workflow.env}

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
        """
        Process and validate inputs against the workflow's input constraints.

        Args:
            req_inputs: The inputs provided by the user
            input_blueprint: The input constraints defined in the workflow

        Returns:
            Dict containing processed and validated inputs

        Raises:
            ValueError: If inputs are missing, have invalid types, or are not defined
        """
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
        processed_inputs = {}

        return processed_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        """
        Validate that a value matches the expected type.

        Args:
            value: The value to check
            input_type: The expected type name ('string', 'number', or 'boolean')

        Returns:
            bool: True if the value matches the expected type, False otherwise

        Raises:
            ValueError: If the input_type is not supported
        """
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

    def _resolve_template(self, value: Any, vars: Dict[str, Any] = {}) -> Any:
        """
        Resolve Jinja2 templates in string values and convert back to the original type.

        Args:
            value: The value that may contain a template
            vars: Additional variables to include in the template context

        Returns:
            The resolved value, maintaining the original type if possible
        """
        # Skip template processing for non-string types and None
        if value is None or not isinstance(value, (str, int, float, bool)):
            return value

        try:
            # Convert to string for template processing
            string_value = str(value)

            # Skip template processing if there are no template markers
            if "{{" not in string_value and "{%" not in string_value:
                return value

            # Set up template with all available variables
            template = Template(string_value, autoescape=True)
            template_vars = {
                "jobs": {**self._workflow.jobs, **self._output_jobs},
                "inputs": self._inputs,
                "env": self._envs,
                "self": self._workflow.model_dump(),
                "secrets": self._default_secrets,
                "output_path": self._output_path,
                "sudo": "sudo" if os.geteuid() != 0 and shutil.which("sudo") else "",
                "run_id": self._id,
                "fapt": 'if [ -z "$( ls -A /var/lib/apt/lists/ )" ]; then apt-get update; fi && apt-fast install -y --no-install-recommends',
                "uv_install": "uv tool install",
                "go_install": "go install -v",
            }

            # Add custom variables if provided
            if vars:
                template_vars.update(vars)

            # Render the template
            result = template.render(template_vars)

            # Convert back to the original type if possible
            if isinstance(value, bool):
                return result.lower() in ("true", "yes", "1", "t", "y")
            elif isinstance(value, int):
                try:
                    return int(result)
                except ValueError:
                    logger.warning(
                        self._produce_log(
                            f"Could not convert template result '{result}' back to integer"
                        )
                    )
                    return result
            elif isinstance(value, float):
                try:
                    return float(result)
                except ValueError:
                    logger.warning(
                        self._produce_log(
                            f"Could not convert template result '{result}' back to float"
                        )
                    )
                    return result

            logger.debug(
                self._produce_log(
                    f"Resolved template for value '{value}' to '{result}'"
                )
            )
            return result

        except Exception as e:
            logger.error(
                self._produce_log(f"Error resolving template for value '{value}': {e}")
            )
            return value

    def _produce_log(self, message: Any) -> str:
        message_str = str(message)
        return f"[{'sub-' if self._is_reused else ''}workflow '{self._workflow.name}']({self._status.value.upper()}) -> {message_str}"

    def resolve_template(self, value: Any, vars: Dict[str, Any] = {}) -> Any:
        """Public method for template resolution"""
        logger.debug(
            self._produce_log(
                f"Resolving template for value '{str(value)}' with vars: {vars}"
            )
        )
        return self._resolve_template(value, vars)

    def get_default_secrets(self) -> Dict[str, Any]:
        """Get default secrets"""
        return self._default_secrets

    def get_output_path(self) -> Path:
        """Get output path"""
        return self._output_path

    @property
    def run_id(self) -> str:
        """Unique identifier for the workflow run."""
        return self._id

    @property
    def workflow(self) -> Workflow:
        """Get the workflow being executed."""
        return self._workflow
