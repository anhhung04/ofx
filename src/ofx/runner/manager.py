import asyncio
import logging
import yaml
import httpx

from pathlib import Path
from typing import Optional, Dict, Any

from ofx.runner.base import RunContext
from ofx.models.workflow import Workflow
from ofx.runner.workflow import WorkflowRunner
from ofx.utils.misc import MetaSingleton, is_remote_path, clone_remote_repo
from ofx.settings import settings, DEFAULT_WORKFLOWS_DIR

logger = logging.getLogger("ofx")


class FlowRunManager(metaclass=MetaSingleton):
    _flows = {}
    _flows_dirs = [DEFAULT_WORKFLOWS_DIR.absolute()]
    _results = {}

    def add(
        self,
        workflow_name: str,
        inputs: Dict[str, Any] = {},
        output: Optional[str] = None,
    ):
        flow = self.find_flow(workflow_name)
        runner = WorkflowRunner(
            workflow=flow,
            ctx=RunContext(inputs=inputs),
            output_path=Path(output) if output else Path.cwd() / "out",
        )
        runner.attach_manager(self)
        bg_task = asyncio.create_task(runner.run())
        run_id = runner.run_id
        self._flows[run_id] = {
            "runner": runner,
            "task": bg_task,
        }
        return run_id

    async def wait(self, task_id: Optional[str] = None):
        """
        Wait for all running flows to complete or for a specific task if task_id is provided.

        Args:
            task_id: Optional ID of the specific task to wait for

        Raises:
            ValueError: If the task_id is provided but not found
            TimeoutError: If waiting for the task exceeds the configured timeout
        """
        if not self._flows:
            logger.debug("No flows to wait for")
            return

        if task_id is not None and task_id not in self._flows:
            logger.warning(f"Task with ID {task_id} not found in flow manager")
            return

        task = self._flows.get(task_id, {}).get("task") if task_id else None

        if task_id and not task:
            raise ValueError(
                f"Task with ID {task_id} not found or not properly initialized"
            )

        try:
            if task:
                await asyncio.wait_for(task, timeout=settings.timeout)
            else:
                tasks = [flow_data["task"] for flow_data in self._flows.values()]
                await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            logger.error(
                f"Timeout waiting for task {task_id or 'all tasks'} to complete"
            )
            raise TimeoutError(
                f"Workflow execution timed out after {settings.timeout} seconds"
            )
        except Exception as e:
            logger.error(
                f"Error while waiting for task {task_id or 'all tasks'}: {str(e)}"
            )
            raise

    @property
    def flows(self):
        return self._flows

    def get_runner(self, id: str):
        return self._flows.get(id)

    def add_workflow_dir(self, path: str):
        if path not in self._flows_dirs:
            self._flows_dirs.append(path)

    def find_flow(self, workflow_name: str) -> Workflow:
        """
        Find and load a workflow from local directories, file path, URL, or git repository.

        Args:
            workflow_name: Name, path, URL, or git repository of the workflow

        Returns:
            Workflow: The loaded workflow

        Raises:
            RuntimeError: If the workflow cannot be found or loaded
        """
        for directory in self._flows_dirs:
            path = Path(directory) / f"{workflow_name.rstrip('.yml')}.yml"
            if path.exists():
                try:
                    return Workflow.model_validate(
                        yaml.safe_load(path.read_text().strip())
                    )
                except Exception as e:
                    logger.error(f"Failed to load workflow from {path}: {e}")
                    raise RuntimeError(f"Failed to load workflow from {path}: {e}")

        if Path(workflow_name).exists():
            try:
                return Workflow.model_validate(
                    yaml.safe_load(Path(workflow_name).read_text().strip())
                )
            except Exception as e:
                logger.error(f"Failed to load workflow from file {workflow_name}: {e}")
                raise RuntimeError(
                    f"Failed to load workflow from file {workflow_name}: {e}"
                )

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

        self.add_workflow_dir(git_path.absolute())
        try:
            return Workflow.model_validate(
                yaml.safe_load((git_path / "main.yml").read_text().strip())
            )
        except Exception as e:
            logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to load workflow from git repo {workflow_name}: {e}"
            )
