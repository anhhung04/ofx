"""Workflow utilities for OFX framework."""

import logging
from functools import lru_cache
from pathlib import Path

import httpx
import yaml

from ofx.models.workflow import Workflow
from ofx.settings import settings
from ofx.utils.git import clone_remote_repo
from ofx.utils.path import find_valid_flow, is_remote_path, is_s3_path
from ofx.utils.s3 import download_s3_workflow


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
    workflow_name: str, search_dirs_tuple: tuple[Path, ...]
) -> tuple[Path, Workflow]:  # type: ignore
    """Find and load a workflow from local directories, file path, URL, or git repository.

    Args:
        workflow_name: Name or path of the workflow to find
        search_dirs_tuple: Tuple of directories to search (tuple for hashability)

    Returns:
        Loaded Workflow object

    Raises:
        RuntimeError: If workflow cannot be found or loaded
    """
    logger = logging.getLogger(settings.app_branding)

    logger.debug(f"Searching for workflow: {workflow_name} in {search_dirs_tuple}")

    workflow_name = workflow_name.strip()
    flow_path = find_valid_flow(Path.cwd(), workflow_name)

    if flow_path:
        try:
            flow = Workflow.model_validate(
                yaml.safe_load(flow_path.read_text().strip())
            )
            flow.workflow_path = flow_path
            return flow_path, flow
        except Exception as e:
            logger.error(f"Failed to load workflow from file {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to load workflow from file {workflow_name}: {e}"
            ) from e

    for directory in search_dirs_tuple:
        path = find_valid_flow(directory, workflow_name)
        if path:
            try:
                workflow = Workflow.model_validate(
                    yaml.safe_load(path.read_text().strip())
                )
                workflow.workflow_path = path
                return path, workflow
            except Exception as e:
                logger.error(f"Failed to load workflow from {path}: {e}")
                raise RuntimeError(f"Failed to load workflow from {path}: {e}") from e

    if is_remote_path(workflow_name):
        try:
            response = httpx.get(workflow_name)
            response.raise_for_status()
            workflow = Workflow.model_validate(yaml.safe_load(response.text.strip()))
            return workflow.workflow_path, workflow
        except Exception as e:
            logger.error(f"Failed to fetch workflow from {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to fetch workflow from {workflow_name}: {e}"
            ) from e

    if is_s3_path(workflow_name):
        try:
            flow_path, content = download_s3_workflow(workflow_name)
            workflow = Workflow.model_validate(yaml.safe_load(content.strip()))
            workflow.workflow_path = flow_path
            logger.info(f"Loaded workflow from S3: {workflow_name}")
            return flow_path, workflow
        except Exception as e:
            logger.error(f"Failed to fetch workflow from S3 {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to fetch workflow from S3 {workflow_name}: {e}"
            ) from e

    git_path = clone_remote_repo(workflow_name)
    if not git_path:
        raise RuntimeError(f"Workflow {workflow_name} not found.") from None

    try:
        main_path = find_valid_flow(git_path, "main")
        if not main_path:
            raise RuntimeError(
                f"No main workflow file found in cloned repo {workflow_name}."
            )
        workflow = Workflow.model_validate(
            yaml.safe_load(main_path.read_text().strip())
        )
        workflow.workflow_path = main_path
        return main_path, workflow
    except Exception as e:
        logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
        raise RuntimeError(
            f"Failed to load workflow from git repo {workflow_name}: {e}"
        ) from e
