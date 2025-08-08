import os
import uuid
import logging

from ofx.runner.base import BaseRunner, RunnerStatus
from ofx.runner.job import JobRunner
from ofx.models.workflow import Workflow

from pathlib import Path
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from jinja2 import Environment
from typing import Optional, Dict, Any

logger = logging.getLogger("ofx")


class WorkflowRunner(BaseRunner):
    _id: str = None

    _envs = {}
    _inputs = {}
    _outputs = {}
    _is_reused: bool = False

    def __init__(
        self,
        workflow: Workflow,
        inputs: Dict[str, Any] = {},
        output: Optional[str] = None,
        is_reused: bool = False,
    ):
        super().__init__(workflow.name)
        self._id = str(uuid.uuid4())
        self._workflow = workflow
        self._is_reused = is_reused
        self._inputs = inputs
        self._output_path = Path(output) if output else None
        self._do_init()

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
            self._status = RunnerStatus.RUNNING
            task_id = progress.add_task(
                description=f"Preparing to run workflow '{self._workflow.name}'",
            )

            total_steps = sum(len(j.steps) for j in self._workflow.jobs.values())
            progress.update(
                task_id,
                description=f"Running {'sub' if self._is_reused else ''}workflow '[bold]{self._workflow.name}[/bold]'",
                total=total_steps,
            )

            async for _ in self._update_progress():
                progress.advance(task_id)
                if progress.finished:
                    progress.update(
                        task_id,
                        description=f"Workflow '[bold]{self._workflow.name}[/bold]' completed successfully.",
                    )

    async def _update_progress(self):
        """Process the workflow steps and update progress."""
        for job_id in self._workflow.jobs:
            job = self._workflow.jobs[job_id]
            job_runner = JobRunner(job)
            job_runner.attach_manager(self._manager)
            job_runner.attach_workflow(self)
            self._outputs[job_id] = {}
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
                async for step_output in job_runner.run():
                    if not self._outputs[job_id]:
                        self._outputs[job_id] = []
                    else:
                        self._outputs[job_id].insert(step_output["id"], step_output)
                    progress.advance(task_id)
                    if progress.finished:
                        progress.update(
                            task_id,
                            description=f"Job '[bold]{job.name}[/bold]' of flow '[bold]{self._workflow.name}[/bold]' completed successfully.",
                        )
                    yield True

    async def _pre_run(self):
        if self._workflow.defaults:
            working_directory = self._workflow.defaults.run.working_directory
            os.chdir(working_directory)
        logger.debug(f"Resolved workflow: {self._workflow.model_dump()}")

    async def _post_run(self) -> Dict[str, Any]:
        return {}

    def _do_init(self):
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

    def _process_inputs(
        self, req_inputs: dict, input_blueprint: dict
    ) -> Dict[str, Any]:
        """Process and validate inputs against the workflow's input constraints."""
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
            processed_inputs[input_name] = self._resolve_template(input_value)
        return processed_inputs

    def _check_input_type(self, value: Any, input_type: str) -> bool:
        """Parse input value based on the specified type."""
        match input_type:
            case "string":
                return isinstance(value, str)
            case "number":
                return isinstance(value, (int, float))
            case "boolean":
                return isinstance(value, bool)
            case _:
                raise ValueError(f"Unsupported input type: {type}")

    def _resolve_template(self, string: str, vars: Dict[str, Any] = {}) -> str:
        env = Environment(autoescape=True)
        tmp = env.from_string(string)
        vars.update({"jobs": {**self._outputs, **self._workflow.jobs}})
        vars.update({"inputs": self._inputs})
        vars.update({"env": self._envs})
        vars.update({"self": self._workflow.model_dump()})
        return tmp.render(vars)

    @property
    def run_id(self) -> str:
        """Unique identifier for the workflow run."""
        return self._id
