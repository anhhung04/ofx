"""Helpers for uploading temporary local content to remote runners."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def upload_temp_content(
    remote: Any,
    content: str,
    remote_path: str,
    *,
    suffix: str = "",
) -> None:
    """Write content to a temp file, upload it, then clean up."""
    fd, local_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    Path(local_path).write_text(content)
    os.chmod(local_path, 0o600)
    try:
        remote.upload(local_path, remote_path)
    finally:
        Path(local_path).unlink(missing_ok=True)


__all__ = ["upload_temp_content"]
