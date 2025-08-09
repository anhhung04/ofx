import git
import tempfile
import json

from collections import deque
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from typing import Optional, Dict, Set, Tuple, List


def is_remote_path(path: str) -> bool:
    """
    Check if the given path is a remote URL (http or https).

    Args:
        path (str): The path to check.

    Returns:
        bool: True if the path is a remote URL, False otherwise.
    """
    return urlparse(path).scheme in ["http", "https"]


def clone_remote_repo(path: str) -> Optional[Path]:
    """
    Check if the given path is a Git repository.

    Args:
        path (str): The path to check.

    Returns:
        Optional[Path]: The path to the cloned repository if it is a Git repository, None otherwise.
    """
    try:
        tmp_dir = tempfile.mkdtemp(prefix=".ofx_")
        repo_name = Path(path).name
        git.Repo.clone_from(path, tmp_dir, multi_options=["--depth=1"])
        return Path(tmp_dir) / repo_name
    except Exception:
        return None


def load_secrets(secrets_dir: Path) -> Dict[str, str]:
    """
    Load secrets from a YAML file in the specified directory.

    Args:
        secrets_dir (Path): The directory where the secrets file is located.

    Returns:
        Dict[str, str]: A dictionary containing the loaded secrets.
    """
    secrets = {}
    for secret_file in secrets_dir.glob("*"):
        content = secret_file.read_text()
        try:
            content = json.loads(content)
        except:
            pass
        secrets[secret_file.name] = content
    return secrets


# kahn's algorithm
def find_parallel_schedule(
    jobs: List[str], dependencies: List[Tuple[str, str]]
) -> List[Set[str]]:
    """
    Groups jobs into stages that can be run in parallel.

    Returns:
        A list of sets, where each set contains jobs that can be run concurrently.
    """
    # Step 1 & 2: Build graph and in-degrees (same as before)
    graph: Dict[str, List[str]] = {job: [] for job in jobs}
    in_degree: Dict[str, int] = {job: 0 for job in jobs}

    for prereq, job in dependencies:
        # Ensure dependencies are valid jobs
        if prereq not in graph or job not in graph:
            continue
        graph[prereq].append(job)
        in_degree[job] += 1

    # Step 3: Initialize the queue
    queue = deque([job for job in jobs if in_degree[job] == 0])

    parallel_schedule = []
    job_count = 0

    # Step 4: Process jobs in stages
    while queue:
        # All jobs currently in the queue can be run in parallel
        stage_size = len(queue)
        current_stage: Set[str] = set()

        for _ in range(stage_size):
            current_job = queue.popleft()
            current_stage.add(current_job)
            job_count += 1

            # Update neighbors
            for next_job in graph[current_job]:
                in_degree[next_job] -= 1
                if in_degree[next_job] == 0:
                    queue.append(next_job)

        parallel_schedule.append(current_stage)

    # Step 5: Check for cycles
    if job_count != len(jobs):
        raise ValueError(
            "A circular dependency was detected. Cannot create a valid schedule."
        )

    return parallel_schedule


# Generic singleton class
class MetaSingleton(type):
    """Metaclass to create a singleton class"""

    __instances: Dict[type, object] = {}
    __spawning: Set[type] = set()

    def __call__(cls, *args, **kwargs) -> object:
        """Redirects each call to the current class to the corresponding single instance"""
        if cls not in MetaSingleton.__instances:
            if cls in MetaSingleton.__spawning:
                raise RuntimeError(
                    f"Singleton {cls.__name__} is already being spawned. Recursive error detected."
                )
            # Spawning new singleton
            MetaSingleton.__spawning.add(cls)
            # If the instance does not already exist, it is created
            MetaSingleton.__instances[cls] = super(MetaSingleton, cls).__call__(
                *args, **kwargs
            )
            MetaSingleton.__spawning.remove(cls)
        # Return the desired object
        return MetaSingleton.__instances[cls]


class EnumEncoder(json.JSONEncoder):
    """Custom JSON encoder for Enums"""

    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)
