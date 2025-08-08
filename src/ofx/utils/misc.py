import git
import tempfile
import json

from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from typing import Optional, Dict, Set


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
