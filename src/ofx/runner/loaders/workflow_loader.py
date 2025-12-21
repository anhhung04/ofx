import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import yaml

from ofx.models.workflow import Workflow
from ofx.settings import DEFAULT_WORKFLOWS_DIR, settings
from ofx.utils.misc import clone_remote_repo, is_remote_path

if TYPE_CHECKING:
    from ofx.runner.workflow import WorkflowRunner

logger = logging.getLogger(settings.app_branding)


class WorkflowLoader:
    """Loader for workflow YAML files with schema validation.
    
    Supports loading workflows from:
    - Local file paths
    - Workflow directories
    - Remote URLs (HTTP/HTTPS)
    - Git repositories
    """
    _flows_dirs = [DEFAULT_WORKFLOWS_DIR.absolute(), Path.cwd().absolute()]

    @classmethod
    def add_workflow_dir(cls, path: Path | str):
        """Add a directory to the workflow search path.
        
        Args:
            path: Directory path to add to search path
        """
        abs_path = Path(path).absolute()
        if abs_path not in cls._flows_dirs:
            cls._flows_dirs.append(abs_path)

    @classmethod
    def get_workflow_dirs(cls) -> list[Path]:
        """Get all configured workflow directories.
        
        Returns:
            List of Path objects for workflow search directories
        """
        return cls._flows_dirs
    
    @classmethod
    def _validate_and_load(cls, yaml_content: str, source: str) -> Workflow:
        """Validate YAML schema and load workflow.
        
        Args:
            yaml_content: Raw YAML content string
            source: Source identifier for error messages
            
        Returns:
            Validated Workflow object
            
        Raises:
            RuntimeError: If YAML is invalid or schema validation fails
        """
        try:
            data = yaml.safe_load(yaml_content.strip())
            if not isinstance(data, dict):
                raise ValueError("Workflow must be a YAML dictionary")
            
            # Validate required top-level fields
            if 'name' not in data:
                raise ValueError("Workflow must have a 'name' field")
            if 'jobs' not in data:
                raise ValueError("Workflow must have a 'jobs' field")
            
            # Pydantic validation handles the rest
            return Workflow.model_validate(data)
        except yaml.YAMLError as e:
            raise RuntimeError(f"Invalid YAML in {source}: {e}")
        except Exception as e:
            raise RuntimeError(f"Schema validation failed for {source}: {e}")

    @classmethod
    def find_flow(cls, workflow_name: str) -> Workflow:
        """Find and load a workflow by name.
        
        Args:
            workflow_name: Name or path of workflow to load
            
        Returns:
            Loaded and validated Workflow object
            
        Raises:
            RuntimeError: If workflow not found or validation fails
        """
        logger.debug(
            f"Searching for workflow: {workflow_name} in {cls._flows_dirs}"
        )

        if Path(workflow_name).exists():
            try:
                flow = cls._validate_and_load(
                    Path(workflow_name).read_text(),
                    f"file {workflow_name}"
                )
                cls.add_workflow_dir(Path(workflow_name).parent.absolute())
                return flow
            except Exception as e:
                logger.error(f"Failed to load workflow from file {workflow_name}: {e}")
                raise

        for directory in cls._flows_dirs:
            path = directory / f"{workflow_name.rstrip('.yml')}.yml"
            if path.exists():
                try:
                    if path.parent.exists():
                        cls.add_workflow_dir(path.parent.absolute())
                    return cls._validate_and_load(
                        path.read_text(),
                        f"directory {path}"
                    )
                except Exception as e:
                    logger.error(f"Failed to load workflow from {path}: {e}")
                    raise

        if is_remote_path(workflow_name):
            try:
                response = httpx.get(workflow_name)
                response.raise_for_status()
                return cls._validate_and_load(
                    response.text,
                    f"URL {workflow_name}"
                )
            except Exception as e:
                logger.error(f"Failed to fetch workflow from {workflow_name}: {e}")
                raise

        git_path = clone_remote_repo(workflow_name)
        if not git_path:
            raise RuntimeError(f"Workflow {workflow_name} not found.")

        cls.add_workflow_dir(git_path.absolute())
        try:
            return cls._validate_and_load(
                (git_path / "main.yml").read_text(),
                f"git repo {workflow_name}"
            )
        except Exception as e:
            logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
            raise
