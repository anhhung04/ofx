import json
import os
import tempfile
from collections import deque
from enum import Enum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import git

from ofx.settings import TOOLS_BIN_DIR

# Cache the tools bin path to avoid repeated Path operations
_TOOLS_BIN_PATH = TOOLS_BIN_DIR.absolute().as_posix()

def populate_env(alt_env=None) -> dict[str, str]:
    """Populate environment variables including tools bin directory.

    Optimized to cache and reuse paths.
    """
    if alt_env is None:
        alt_env = {}

    envs = os.environ.copy()
    current_path = envs.get("PATH", "")
    if _TOOLS_BIN_PATH not in current_path:
        envs["PATH"] = f"{_TOOLS_BIN_PATH}{os.pathsep}{current_path}"
    # Set UV_TOOL_BIN_DIR for uv tool installations
    envs["UV_TOOL_BIN_DIR"] = _TOOLS_BIN_PATH
    envs.update(alt_env)
    return envs

@lru_cache(maxsize=128)
def is_remote_path(path: str) -> bool:
    """Check if the given path is a remote URL (http or https).

    Cached for repeated checks.
    """
    return urlparse(path).scheme in ["http", "https"]


def clone_remote_repo(path: str) -> Path | None:
    """Check if the given path is a Git repository"""
    try:
        tmp_dir = tempfile.mkdtemp(prefix=".ofx_")
        repo_name = Path(path).name
        git.Repo.clone_from(path, tmp_dir, multi_options=["--depth=1"])
        return Path(tmp_dir) / repo_name
    except Exception:
        return None


def load_secrets(secrets_dir: Path = None) -> dict[str, str]:
    from ofx.utils.secrets import SecretManager

    secrets = SecretManager.list()

    if not secrets and secrets_dir and secrets_dir.exists():
        for secret_file in secrets_dir.glob("*"):
            content = secret_file.read_text()
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                pass
            secrets[secret_file.name] = content

    return secrets


def find_parallel_schedule(
    jobs: list[str], dependencies: list[tuple[str, str]]
) -> list[set[str]]:
    """Groups jobs into stages that can be run in parallel.

    Uses topological sorting with BFS for optimal parallelization.
    """
    # Pre-allocate with dict comprehension for better performance
    graph: dict[str, list[str]] = {job: [] for job in jobs}
    in_degree: dict[str, int] = dict.fromkeys(jobs, 0)

    for prereq, job in dependencies:
        if prereq not in graph or job not in graph:
            continue
        graph[prereq].append(job)
        in_degree[job] += 1

    queue = deque([job for job in jobs if in_degree[job] == 0])

    parallel_schedule = []
    job_count = 0

    while queue:
        stage_size = len(queue)
        current_stage: set[str] = set()

        for _ in range(stage_size):
            current_job = queue.popleft()
            current_stage.add(current_job)
            job_count += 1

            for next_job in graph[current_job]:
                in_degree[next_job] -= 1
                if in_degree[next_job] == 0:
                    queue.append(next_job)

        parallel_schedule.append(current_stage)

    if job_count != len(jobs):
        raise ValueError(
            "A circular dependency was detected. Cannot create a valid schedule."
        )

    return parallel_schedule


class MetaSingleton(type):
    """Metaclass to create a singleton class"""

    __instances: dict[type, object] = {}
    __spawning: set[type] = set()

    def __call__(cls, *args, **kwargs) -> object:
        """Redirects each call to the current class to the corresponding single instance"""
        if cls not in MetaSingleton.__instances:
            if cls in MetaSingleton.__spawning:
                raise RuntimeError(
                    f"Singleton {cls.__name__} is already being spawned. Recursive error detected."
                )
            MetaSingleton.__spawning.add(cls)
            MetaSingleton.__instances[cls] = super().__call__(
                *args, **kwargs
            )
            MetaSingleton.__spawning.remove(cls)
        return MetaSingleton.__instances[cls]


class EnumEncoder(json.JSONEncoder):
    """Custom JSON encoder for Enums"""

    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


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
def find_workflow(workflow_name: str, search_dirs_tuple: tuple[Path, ...]) -> "Workflow":
    """Find and load a workflow from local directories, file path, URL, or git repository.
    
    Args:
        workflow_name: Name or path of the workflow to find
        search_dirs_tuple: Tuple of directories to search (tuple for hashability)
        
    Returns:
        Loaded Workflow object
        
    Raises:
        RuntimeError: If workflow cannot be found or loaded
    """
    import logging
    import httpx
    import yaml
    from ofx.models.workflow import Workflow
    from ofx.settings import settings
    
    logger = logging.getLogger(settings.app_branding)
    search_dirs = list(search_dirs_tuple)
    
    logger.debug(f"Searching for workflow: {workflow_name} in {search_dirs}")

    if Path(workflow_name).exists():
        try:
            flow = Workflow.model_validate(
                yaml.safe_load(Path(workflow_name).read_text().strip())
            )
            return flow
        except Exception as e:
            logger.error(f"Failed to load workflow from file {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to load workflow from file {workflow_name}: {e}"
            ) from e

    for directory in search_dirs:
        path = directory / f"{workflow_name.rstrip('.yml')}.yml"
        if path.exists():
            try:
                return Workflow.model_validate(
                    yaml.safe_load(path.read_text().strip())
                )
            except Exception as e:
                logger.error(f"Failed to load workflow from {path}: {e}")
                raise RuntimeError(f"Failed to load workflow from {path}: {e}") from e

    if is_remote_path(workflow_name):
        try:
            response = httpx.get(workflow_name)
            response.raise_for_status()
            return Workflow.model_validate(yaml.safe_load(response.text.strip()))
        except Exception as e:
            logger.error(f"Failed to fetch workflow from {workflow_name}: {e}")
            raise RuntimeError(
                f"Failed to fetch workflow from {workflow_name}: {e}"
            ) from e

    git_path = clone_remote_repo(workflow_name)
    if not git_path:
        raise RuntimeError(f"Workflow {workflow_name} not found.") from None

    try:
        return Workflow.model_validate(
            yaml.safe_load((git_path / "main.yml").read_text().strip())
        )
    except Exception as e:
        logger.error(f"Failed to load workflow from git repo {workflow_name}: {e}")
        raise RuntimeError(
            f"Failed to load workflow from git repo {workflow_name}: {e}"
        ) from e
