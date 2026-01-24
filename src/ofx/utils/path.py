"""Path utilities for OFX framework."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from git import Git

from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS


@lru_cache(maxsize=128)
def is_remote_path(path: str) -> bool:
    """Check if the given path is a remote URL (http or https).

    Cached for repeated checks.
    """
    return urlparse(path).scheme in ["http", "https"]


@lru_cache(maxsize=128)
def is_git_repo(url: str) -> bool:
    """Check if the given URL is a remote Git repo"""
    try:
        Git().ls_remote(url)
        return True
    except:
        return False


def find_valid_flow(dir: Path, name: str) -> Path | None:
    """Check if a workflow file exists in the given directory."""
    for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
        flow_path = dir / name
        flow_path = flow_path.with_suffix(ext)
        if flow_path.exists():
            return flow_path
    else:
        return None
