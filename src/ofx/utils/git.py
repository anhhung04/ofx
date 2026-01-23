"""Git utilities for OFX framework."""

import tempfile
from pathlib import Path

import git


def clone_remote_repo(path: str) -> Path | None:
    """Check if the given path is a Git repository"""
    try:
        tmp_dir = tempfile.mkdtemp(prefix=".ofx_")
        repo_name = Path(path).name
        git.Repo.clone_from(path, tmp_dir, multi_options=["--depth=1"])
        return Path(tmp_dir) / repo_name
    except Exception:
        return None
