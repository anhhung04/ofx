"""Git utilities for OFX framework."""

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import git


def clone_remote_repo(
    path: str, default_registry: str = "https://github.com"
) -> Path | None:
    """Check if the given path is a Git repository"""
    try:
        ref = ""
        if "@" in path:
            path, ref = path.split("@")
        remote_url = urlparse(path)
        if not remote_url.netloc:
            default_url = urlparse(default_registry)
            remote_url = remote_url._replace(
                scheme=default_url.scheme,
                netloc=default_url.netloc,
            )
            path = remote_url.geturl()
        tmp_dir = tempfile.mkdtemp(prefix=".ofx_")
        repo_name = Path(path).name
        opts = ["--depth=1"]
        if ref:
            opts.append(f"--branch={ref}")
        git.Repo.clone_from(path, tmp_dir, multi_options=opts)
        return Path(tmp_dir) / repo_name
    except Exception:
        return None
