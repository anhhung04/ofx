"""Workflow utilities for OFX framework."""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import yaml

from ofx.models.workflow import Workflow
from ofx.settings import settings
from ofx.utils.git import clone_remote_repo
from ofx.utils.path import find_valid_flow, is_git_repo, is_remote_path

logger = logging.getLogger(settings.app_branding)


def coerce_input_value(value: Any, expected_type: str, name: str = "") -> Any:
    """Coerce an input value to the expected workflow input type.

    Handles values that may already be JSON-decoded by the CLI parser.

    Args:
        value: The value to coerce.
        expected_type: One of ``"string"``, ``"number"``, ``"boolean"``,
            ``"array"``, ``"object"``.
        name: Input name used in error messages.

    Returns:
        The coerced value.

    Raises:
        ValueError: If coercion is not possible.
    """
    if expected_type == "number":
        # bool is a subclass of int — reject it explicitly
        if isinstance(value, bool):
            raise ValueError(
                f"Cannot convert boolean '{value}' to number for input '{name}'"
            )
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return int(value) if "." not in value else float(value)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Cannot convert '{value}' to number for input '{name}'"
                ) from None
        raise ValueError(
            f"Cannot convert {type(value).__name__} to number for input '{name}'"
        )

    elif expected_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            if value.lower() in ("true", "yes", "1", "y"):
                return True
            if value.lower() in ("false", "no", "0", "n"):
                return False
            raise ValueError(
                f"Cannot convert '{value}' to boolean for input '{name}' "
                "(use true/false/yes/no/1/0)"
            )
        raise ValueError(
            f"Cannot convert {type(value).__name__} to boolean for input '{name}'"
        )

    elif expected_type == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            raise ValueError(
                f"Cannot convert '{value}' to array for input '{name}' "
                '(use JSON array syntax: ["a", "b"])'
            )
        raise ValueError(
            f"Cannot convert {type(value).__name__} to array for input '{name}'"
        )

    elif expected_type == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            raise ValueError(
                f"Cannot convert '{value}' to object for input '{name}' "
                '(use JSON object syntax: {{"key": "value"}})'
            )
        raise ValueError(
            f"Cannot convert {type(value).__name__} to object for input '{name}'"
        )

    elif expected_type == "string":
        if not isinstance(value, str):
            return str(value)
        return value

    # Unknown type — pass through
    return value


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


def find_workflow(
    workflow_name: str,
    search_dirs_tuple: tuple[Path, ...],
    flow_registry_url: str = "https://github.com",
) -> Workflow:
    """Find and load a workflow from local directories, file path, URL, or git repository.

    Each call returns an independent deep copy so callers can safely mutate
    the model (e.g. template resolution) without corrupting the cache.

    Args:
        workflow_name: Name or path of the workflow to find
        search_dirs_tuple: Tuple of directories to search (tuple for hashability)

    Returns:
        Loaded Workflow object (deep copy — safe to mutate)

    Raises:
        RuntimeError: If workflow cannot be found or loaded
    """
    cached = _find_workflow_cached(workflow_name, search_dirs_tuple, flow_registry_url)
    return cached.model_copy(deep=True)


@lru_cache(maxsize=32)
def _find_workflow_cached(
    workflow_name: str,
    search_dirs_tuple: tuple[Path, ...],
    flow_registry_url: str = "https://github.com",
) -> Workflow:
    """Internal cached loader — returns a shared reference. Do NOT mutate."""
    logger.debug(f"Searching for workflow: {workflow_name} in {search_dirs_tuple}")
    workflow_name = workflow_name.strip()

    if workflow_name.startswith(("/", ".")):
        flow_path = Path(workflow_name)
        if flow_path.is_absolute():
            try:
                flow = Workflow.model_validate(
                    yaml.safe_load(flow_path.read_text().strip())
                )
            except yaml.YAMLError as e:
                raise RuntimeError(
                    f"Invalid YAML in workflow file {flow_path}: {e}"
                ) from None
            flow.workflow_path = flow_path
            return flow

        for directory in search_dirs_tuple:
            path = find_valid_flow(directory, workflow_name)
            if not path:
                continue
            try:
                workflow = Workflow.model_validate(
                    yaml.safe_load(path.read_text().strip())
                )
            except yaml.YAMLError as e:
                raise RuntimeError(
                    f"Invalid YAML in workflow file {path}: {e}"
                ) from None
            workflow.workflow_path = path
            return workflow
        else:
            raise RuntimeError(f"Workflow {workflow_name} not found in local paths.")

    # Search for workflow by name in search directories
    for directory in search_dirs_tuple:
        path = find_valid_flow(directory, workflow_name)
        if not path:
            continue
        try:
            workflow = Workflow.model_validate(
                yaml.safe_load(path.read_text().strip())
            )
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"Invalid YAML in workflow file {path}: {e}"
            ) from None
        workflow.workflow_path = path
        return workflow

    if is_remote_path(workflow_name) and not is_git_repo(workflow_name):
        response = httpx.get(workflow_name, timeout=30)
        response.raise_for_status()
        try:
            workflow = Workflow.model_validate(
                yaml.safe_load(response.text.strip())
            )
        except yaml.YAMLError as e:
            raise RuntimeError(
                f"Invalid YAML in remote workflow {workflow_name}: {e}"
            ) from None
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
    try:
        workflow = Workflow.model_validate(
            yaml.safe_load(main_path.read_text().strip())
        )
    except yaml.YAMLError as e:
        raise RuntimeError(
            f"Invalid YAML in cloned workflow {main_path}: {e}"
        ) from None
    workflow.workflow_path = main_path
    return workflow


def list_available_workflows(search_dirs: tuple[str | Path, ...]) -> list[str]:
    """List all available workflow names from search directories."""
    workflows: list[str] = []
    for d in search_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in d.rglob("*.yml"):
            workflows.append(f.stem)
        for f in d.rglob("*.yaml"):
            workflows.append(f.stem)
    return sorted(set(workflows))


def find_all_workflows(search_dirs: list[Path]) -> list[Path]:
    """Find all workflow files in the specified directories.

    Args:
        search_dirs: List of directories to search
    Returns:
        List of paths to valid workflow files
    """
    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS

    workflow_files: list[Path] = []
    for directory in search_dirs:
        if not directory.exists():
            continue

        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            workflow_files.extend(directory.glob(f"*{ext}"))

    return sorted(set(workflow_files))  # Deduplicate and sort
