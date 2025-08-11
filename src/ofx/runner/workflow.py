import os
import asyncio
import yaml
import httpx
import logging

from ofx.runner.base import BaseRunner, RunnerStatus
from ofx.runner.job import JobRunner
from ofx.models.workflow import Workflow
from ofx.settings import SECRETS_DIR, DEFAULT_WORKFLOWS_DIR, settings
from ofx.utils.misc import (
    load_secrets,
    find_parallel_schedule,
    is_remote_path,
    clone_remote_repo,
    MetaSingleton,
)

from pathlib import Path
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from jinja2 import Template
from typing import Optional, Dict, Any
from asyncstdlib import zip_longest


logger = logging.getLogger("ofx")


class WorkflowRunner(BaseRunner):
    pass


class FlowRunManager(metaclass=MetaSingleton):
    _flows = {}
    _flows_dirs = [DEFAULT_WORKFLOWS_DIR.absolute()]
    _results = {}

    def add(
        self,
        workflow_name: str,
        **kwargs,
    ):
        flow = self.find_flow(workflow_name)
        runner = WorkflowRunner(workflow=flow, **kwargs)
        runner.attach_manager(self)
        bg_task = asyncio.create_task(runner.run())
        self._flows[runner.run_id] = {
            "runner": runner,
            "task": bg_task,
        }
        return runner.run_id

    async def wait(self, task_id: Optional[str] = None):
        """
        Wait for all running flows to complete.
        """
        if not self._flows or task_id not in self._flows:
            return
        task = self._flows.get(task_id, {}).get("task")
        if not task:
            raise ValueError(f"Task with ID {task_id} not found.")
        await asyncio.wait_for(task, timeout=settings.timeout)

    @property
    def flows(self):
        return self._flows

    def get_runner(self, id: str):
        return self._flows.get(id)

    def add_workflow_dir(self, path: str):
        if path not in self._flows_dirs:
            self._flows_dirs.append(path)

    def find_flow(self, workflow_name: str) -> Optional[WorkflowRunner]:
        found_workflow = None
        for dir in self._flows_dirs:
            path = Path(dir) / f"{workflow_name.rstrip('.yml')}.yml"
            if path.exists():
                found_workflow = Workflow.model_validate(
                    yaml.safe_load(path.read_text().strip())
                )
                break
        else:
            if Path(workflow_name).exists():
                found_workflow = Workflow.model_validate(
                    yaml.safe_load(Path(workflow_name).read_text().strip())
                )
            elif is_remote_path(workflow_name):
                found_workflow = Workflow.model_validate(
                    yaml.safe_load(httpx.get(path).text.strip())
                )
        if found_workflow is None:
            git_path = clone_remote_repo(workflow_name)
            if not git_path:
                raise RuntimeError(f"Workflow {workflow_name} not found.")
            self.add_workflow_dir(git_path.absolute())
            found_workflow = Workflow.model_validate(
                yaml.safe_load((git_path / "main.yml").read_text().strip())
            )
        assert found_workflow is not None, f"Workflow {workflow_name} not found."
        return found_workflow


class WorkflowRunner(BaseRunner):
    _envs = {}
    _inputs = {}
    _output_jobs = {}
    _is_reused: bool = False
    _manager: Optional[FlowRunManager] = None
    _job_status = {}

    def __init__(
        self,
        workflow: Workflow,
        inputs: Dict[str, Any] = {},
        output: Optional[str] = None,
        is_reused: bool = False,
        secrets: Optional[Dict[str, Any]] = None,
        envs: Optional[Dict[str, str]] = None,
    ):
        super().__init__(workflow.name)
        self._workflow = workflow
        self._is_reused = is_reused
        self._inputs = inputs
        self._output_path = Path(output) if output else Path.cwd() / "out"
        self._default_secrets = load_secrets(SECRETS_DIR)
        self._do_init()
        if secrets:
            self._default_secrets.update(secrets)
        if envs:
            self._envs.update(envs)

    async def get_job_status(self, job_id: str) -> RunnerStatus:
        return self._job_status.get(job_id, RunnerStatus.IDLE)

    async def _do_run(self) -> Dict[str, Any]:
        logger.debug(
            f"Running workflow: {self._workflow.name} with inputs: {self._inputs}"
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=self._is_reused,
        ) as progress:
            task_id = progress.add_task(
                description=f"Preparing to run workflow '{self._workflow.name}'",
            )
            total_steps = self._planning_jobs()
            progress.update(
                task_id,
                description=f"Running {'sub-' if self._is_reused else ''}workflow '[bold]{self._workflow.name}[/bold]'",
                total=total_steps,
            )

            async for _ in self._update_progress():
                progress.advance(task_id)
                if progress.finished:
                    progress.update(
                        task_id,
                        description=f"Workflow '[bold]{self._workflow.name}[/bold]' completed.",
                    )

    def _planning_jobs(self) -> int:
        jobs = list(self._workflow.jobs.keys())
        deps = []
        for j_id, j in self._workflow.jobs.items():
            if j.needs:
                if isinstance(j.needs, str):
                    j.needs = [j.needs]
                for dep in j.needs:
                    if dep and dep not in jobs:
                        raise ValueError(
                            f"Job '{j.name}' depends on '{dep}', which is not defined in the workflow."
                        )
                    deps.append((dep, j_id))
        self._schedule = find_parallel_schedule(jobs, deps)
        total_steps = 0
        for stage in self._schedule:
            max_step = max(
                [len(self._workflow.jobs[job_id].steps) for job_id in stage], default=0
            )
            total_steps += max_step
        logger.debug(
            f"Scheduled workflow '{self._workflow.name}' with stages: {self._schedule}"
        )
        return total_steps

    async def _update_progress(self):
        """Process the workflow steps and update progress."""
        for stage in self._schedule:
            logger.debug(f"Running stage with jobs: {stage}")
            async for job_res in zip_longest(
                *[self._run_job(job_id) for job_id in stage], fillvalue=None
            ):
                for i, jr in enumerate(job_res):
                    if jr is False:
                        self._job_status[stage[i]] = RunnerStatus.FAILED
                yield True

    async def _run_job(self, job_id: str):
        job = self._workflow.jobs[job_id]
        job_runner = JobRunner(job)
        job_runner.attach_manager(self._manager)
        job_runner.attach_context_provider(self)  # Use the new method
        self._output_jobs[job_id] = self._workflow.jobs.get(job_id).model_dump()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=True,
        ) as progress:
            task_id = progress.add_task(
                description=f"Running job '{job.name}'",
                total=len(job.steps),
            )
            try:
                async for step_output in job_runner.run():
                    self._output_jobs[job_id]["steps"][step_output["id"]].update(
                        step_output
                    )
                    progress.advance(task_id)
                    if progress.finished:
                        progress.update(
                            task_id,
                            description=f"Job '[bold]{job.name}[/bold]' of flow '[bold]{self._workflow.name}[/bold]' completed successfully.",
                        )
                    yield step_output
                yield True
            except:
                yield False

    async def _pre_run(self):
        if self._workflow.defaults:
            working_directory = self._workflow.defaults.run.working_directory
            os.chdir(working_directory)
        logger.debug(f"Resolved workflow: {self._workflow.model_dump()}")

    async def _post_run(self) -> Dict[str, Any]:
        if self._status == RunnerStatus.FAILED:
            logger.error(
                f"Workflow '{self._workflow.name}' failed with error: {self._error}"
            )
        self._result["outputs"] = self._output_jobs
        if self._is_reused and self._workflow.workflow_call:
            self._result["outputs"] = {}
            for k, v in self._workflow.workflow_call.outputs.items():
                self._result["outputs"][k] = self._resolve_template(
                    v, self._output_jobs
                )
        self._result["workflow"] = self._workflow.model_dump()
        self._result["run_id"] = self._id
        self._result["status"] = self._status
        self._result["inputs"] = self._inputs
        self._result["envs"] = self._envs
        self._result["output_path"] = str(self._output_path)

    def _do_init(self):
        if not self._output_path.exists():
            self._output_path.mkdir(parents=True, exist_ok=True)
        self._stdout = logging.Logger("ofx.stdout-" + self._id)
        self._stdout.addHandler(
            logging.FileHandler(self._output_path / "stdout.log", mode="a+")
        )
        logger.debug(
            f"Workflow '{self._workflow.name}' dispatch inputs: {self._workflow.workflow_dispatch.inputs}"
        )
        logger.debug(
            f"Workflow '{self._workflow.name}' call inputs: {self._workflow.workflow_call.inputs}"
        )

        if self._workflow.workflow_dispatch and not self._is_reused:
            self._inputs.update(
                self._process_inputs(
                    self._inputs, self._workflow.workflow_dispatch.inputs
                )
            )
        if self._workflow.workflow_call and self._is_reused:
            self._inputs.update(
                self._process_inputs(self._inputs, self._workflow.workflow_call.inputs)
            )
            self._default_secrets.update(
                self._process_inputs(
                    self._default_secrets, self._workflow.workflow_call.secrets
                )
            )

        self._envs = {**os.environ, **self._workflow.env}
        logger.debug(
            f"Initialized workflow runner for '{self._workflow.name}' with ID '{self._id}'"
        )
        logger.debug(f"Workflow inputs: {self._inputs}")
        logger.debug(f"Workflow environment: {self._envs}")
        logger.debug(f"Workflow output path: {self._output_path}")
        logger.debug(f"Workflow default secrets: {self._default_secrets}")

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
        """Process and validate inputs against the workflow's input constraints."""
        logger.debug(
            f"Processing inputs from workflow {'dispath' if self._is_reused else 'call'}: {req_inputs} with blueprint: {input_blueprint}"
        )
        processed_inputs = {}
        for input_name, input_value in req_inputs.items():
            if input_name not in input_blueprint:
                raise ValueError(
                    f"Input '{input_name}' is not defined in the workflow."
                )
            input_constraint = input_blueprint[input_name]
            if input_constraint.required and input_value is None:
                raise ValueError(f"Input '{input_name}' is required but not provided.")
            if input_value is not None and not self._check_input_type(
                input_value, input_constraint.type
            ):
                raise ValueError(
                    f"Input '{input_name}' has an invalid type. Expected {input_constraint.type}, got {type(input_value)}."
                )
            elif input_blueprint[input_name].default:
                input_value = input_blueprint[input_name].default
            processed_inputs[input_name] = self._resolve_template(input_value)
        return processed_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        """Parse input value based on the specified type."""
        if input_type is "string":
            return isinstance(value, str)
        elif input_type is "number":
            return isinstance(value, (int, float))
        elif input_type is "boolean":
            return isinstance(value, bool)
        raise ValueError(
            f"Unsupported input type '{input_type}' for value '{value}'. Supported types are: string, number, boolean."
        )

    def _resolve_template(self, string: str, vars: Dict[str, Any] = {}) -> str:
        tmp = Template(str(string))
        vars.update({"jobs": {**self._output_jobs, **self._workflow.jobs}})
        vars.update({"inputs": self._inputs})
        vars.update({"env": self._envs})
        vars.update({"self": self._workflow.model_dump()})
        vars.update({"secrets": self._default_secrets})
        vars.update({"output_path": self._output_path})
        return tmp.render(vars)

    def resolve_template(self, string: str, vars: Dict[str, Any] = {}) -> str:
        """Public method for template resolution"""
        return self._resolve_template(string, vars)

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
