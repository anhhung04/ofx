import json
import tempfile
from collections import deque
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from ofx.settings import TOOLS_BIN_DIR

import git
import os

def populate_env(alt_env={}) -> Dict[str, str]:
    """Populate environment variables including tools bin directory"""
    envs = os.environ.copy()
    tools_bin_path = TOOLS_BIN_DIR.absolute().as_posix()
    current_path = envs.get("PATH", "")
    if tools_bin_path not in current_path:
        envs["PATH"] = f"{tools_bin_path}{os.pathsep}{current_path}"
    # Set UV_TOOL_BIN_DIR for uv tool installations
    envs["UV_TOOL_BIN_DIR"] = tools_bin_path
    for k, v in alt_env.items():
        envs[k] = v
    return envs

def is_remote_path(path: str) -> bool:
    """Check if the given path is a remote URL (http or https)"""
    return urlparse(path).scheme in ["http", "https"]


def clone_remote_repo(path: str) -> Optional[Path]:
    """Check if the given path is a Git repository"""
    try:
        tmp_dir = tempfile.mkdtemp(prefix=".ofx_")
        repo_name = Path(path).name
        git.Repo.clone_from(path, tmp_dir, multi_options=["--depth=1"])
        return Path(tmp_dir) / repo_name
    except Exception:
        return None


def load_secrets(secrets_dir: Path = None) -> Dict[str, str]:
    from ofx.utils.secrets import SecretManager

    secrets = SecretManager.list()

    if not secrets and secrets_dir and secrets_dir.exists():
        for secret_file in secrets_dir.glob("*"):
            content = secret_file.read_text()
            try:
                content = json.loads(content)
            except:
                pass
            secrets[secret_file.name] = content

    return secrets


def find_parallel_schedule(
    jobs: List[str], dependencies: List[Tuple[str, str]]
) -> List[Set[str]]:
    """Groups jobs into stages that can be run in parallel"""
    graph: Dict[str, List[str]] = {job: [] for job in jobs}
    in_degree: Dict[str, int] = {job: 0 for job in jobs}

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
        current_stage: Set[str] = set()

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

    __instances: Dict[type, object] = {}
    __spawning: Set[type] = set()

    def __call__(cls, *args, **kwargs) -> object:
        """Redirects each call to the current class to the corresponding single instance"""
        if cls not in MetaSingleton.__instances:
            if cls in MetaSingleton.__spawning:
                raise RuntimeError(
                    f"Singleton {cls.__name__} is already being spawned. Recursive error detected."
                )
            MetaSingleton.__spawning.add(cls)
            MetaSingleton.__instances[cls] = super(MetaSingleton, cls).__call__(
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
