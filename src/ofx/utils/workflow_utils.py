"""Workflow utilities for OFX framework."""

import logging
from functools import lru_cache
from pathlib import Path

import httpx
import yaml

from ofx.models.workflow import Workflow
from ofx.settings import settings
from ofx.utils.git import clone_remote_repo
from ofx.utils.path import find_valid_flow, is_git_repo, is_remote_path

logger = logging.getLogger(settings.app_branding)


def add_workflow_dir(workflow_dirs: list[Path], path: Path | str) -> list[Path]:
    """Add a workflow directory to the search path if not already present.

    Args:
        workflow_dirs: Current list of workflow directories
        path: Path to add

    Returns:
        Updated list of workflow directories
    """
    abs_path = Path(path).absolute()
    if abs_path not in workflow_dirs:
        workflow_dirs.append(abs_path)
    return workflow_dirs


@lru_cache(maxsize=32)
def find_workflow(
    workflow_name: str,
    search_dirs_tuple: tuple[Path, ...],
    flow_registry_url: str = "https://github.com",
) -> Workflow:
    """Find and load a workflow from local directories, file path, URL, or git repository.

    Args:
        workflow_name: Name or path of the workflow to find
        search_dirs_tuple: Tuple of directories to search (tuple for hashability)

    Returns:
        Loaded Workflow object

    Raises:
        RuntimeError: If workflow cannot be found or loaded
    """
    logger.debug(f"Searching for workflow: {workflow_name} in {search_dirs_tuple}")
    workflow_name = workflow_name.strip()

    if workflow_name.startswith(("/", ".")):
        flow_path = Path(workflow_name)
        if flow_path.is_absolute():
            flow = Workflow.model_validate(
                yaml.safe_load(flow_path.read_text().strip())
            )
            flow.workflow_path = flow_path
            return flow

        for directory in search_dirs_tuple:
            path = find_valid_flow(directory, workflow_name)
            if not path:
                continue
            workflow = Workflow.model_validate(yaml.safe_load(path.read_text().strip()))
            workflow.workflow_path = path
            return workflow
        else:
            raise RuntimeError(f"Workflow {workflow_name} not found in local paths.")

    if is_remote_path(workflow_name) and not is_git_repo(workflow_name):
        response = httpx.get(workflow_name)
        response.raise_for_status()
        workflow = Workflow.model_validate(yaml.safe_load(response.text.strip()))
        workflow.workflow_path = Path.cwd()
        return workflow

    git_path = clone_remote_repo(workflow_name, flow_registry_url)
    if not git_path:
        raise RuntimeError(f"Workflow {workflow_name} not found.") from None

    main_path = find_valid_flow(git_path, "action")
    if not main_path:
        raise RuntimeError(
            f"No main workflow file found in cloned repo {workflow_name}."
        )
    workflow = Workflow.model_validate(yaml.safe_load(main_path.read_text().strip()))
    workflow.workflow_path = main_path
    return workflow
