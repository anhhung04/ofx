"""Path utilities for OFX framework."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS


@lru_cache(maxsize=128)
def is_remote_path(path: str) -> bool:
    """Check if the given path is a remote URL (http or https).

    Cached for repeated checks.
    """
    return urlparse(path).scheme in ["http", "https"]


@lru_cache(maxsize=128)
def is_s3_path(path: str) -> bool:
    """Check if the given path is an S3 URI (s3://).

    Case-sensitive check for lowercase 's3' scheme.
    Cached for repeated checks.
    """
    parsed = urlparse(path)
    return parsed.scheme == "s3" and path.startswith("s3://")


def find_valid_flow(dir: Path, name: str) -> Path | None:
    """Check if a workflow file exists in the given directory."""
    for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
        flow_path = dir / name
        flow_path = flow_path.with_suffix(ext)
        if flow_path.exists():
            return flow_path
    else:
        return None
