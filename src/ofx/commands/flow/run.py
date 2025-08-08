import asyncio
import yaml
import json
import httpx
import logging

from ofx.runner.workflow import WorkflowRunner
from ofx.utils.misc import MetaSingleton
from ofx.settings import DEFAULT_WORKFLOWS_DIR, settings
from ofx.models.workflow import Workflow
from ofx.utils.misc import is_remote_path, clone_remote_repo

from typing import Optional, List
from pathlib import Path

logger = logging.getLogger("ofx")


class FlowRunManager(metaclass=MetaSingleton):
    _flows = {}
    _flows_dirs = [DEFAULT_WORKFLOWS_DIR.absolute()]
    _results = {}

    def add(
        self,
        workflow_name: str,
        inputs: dict = {},
        output: Optional[str] = None,
        is_reused: bool = False,
    ):
        flow = self.find_flow(workflow_name)
        runner = WorkflowRunner(
            workflow=flow, inputs=inputs, output=output, is_reused=is_reused
        )
        runner.attach_manager(self)
        bg_task = asyncio.create_task(runner.run())
        self._flows[runner.run_id] = bg_task
        return runner.run_id

    async def wait(self, task_id: Optional[str] = None):
        """
        Wait for all running flows to complete.
        """
        if not self._flows or task_id not in self._flows:
            return
        task = self._flows[task_id]
        await asyncio.wait_for(task, timeout=settings.timeout)

    @property
    def flows(self):
        return self._flows

    def get_runner(self, id: str) -> Optional[WorkflowRunner]:
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


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: Optional[List[str]] = None,
        output: Optional[str] = None,
    ):
        self.workflow_name = workflow_name
        self.input = input
        self.output = output
        self.manager = FlowRunManager()

    async def run(self):
        self._process_inputs()
        task_id = self.manager.add(self.workflow_name, self.input, self.output)
        await self.manager.wait(task_id)

    def _process_inputs(self):
        processed_inputs = {}
        for inp in self.input or []:
            try:
                key, value = inp.split("=", 1)
            except:
                raise ValueError(f"Invalid input format: {inp}. Expected key=value.")
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            if key not in processed_inputs:
                processed_inputs[key] = [value]
            else:
                processed_inputs[key].append(value)
        for key in processed_inputs:
            if len(processed_inputs[key]) == 1:
                processed_inputs[key] = processed_inputs[key][0]
        logger.debug(f"Processed inputs: {processed_inputs}")
        self.input = processed_inputs
