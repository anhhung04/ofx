"""Git utilities for OFX framework."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import git

from ofx.settings import TEMP_DIR, ensure_dir, settings

logger = logging.getLogger("ofx")

_REPO_CACHE_DIR = TEMP_DIR / "repos"

def _normalize_repo_name(url: str) -> str:
    name = Path(urlparse(url).path).name
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"

def _cache_key(url: str, ref: str) -> str:
    key = f"{url}@{ref}" if ref else url
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]

def clone_remote_repo(path: str, default_registry: str | None) -> Path | None:
    """Clone a remote repo into a shared cache and reuse if already present."""
    try:
        if not default_registry:
            default_registry = settings.default_remote_registry
        ref = ""
        if "@" in path:
            path, ref = path.split("@", 1)
        remote_url = urlparse(path)
        if not remote_url.netloc:
            default_url = urlparse(default_registry)
            remote_url = remote_url._replace(
                scheme=default_url.scheme,
                netloc=default_url.netloc,
            )
            path = remote_url.geturl()
        ensure_dir(_REPO_CACHE_DIR)
        repo_name = _normalize_repo_name(path)
        cache_dir = _REPO_CACHE_DIR / _cache_key(path, ref) / repo_name
        if (cache_dir / ".git").exists():
            return cache_dir
        cache_dir.parent.mkdir(parents=True, exist_ok=True)
        opts = ["--depth=1"]
        if ref:
            opts.append(f"--branch={ref}")
        git.Repo.clone_from(path, str(cache_dir), multi_options=opts)
        return cache_dir
    except Exception as e:
        logger.warning("Git clone failed for '%s': %s", path, e)
        return None
