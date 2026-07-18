"""Temporary file helpers for the runner subsystem."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

def make_temp_file(*, prefix: str = ".tmp_", suffix: str = ".txt") -> Path:
    """Create a temporary file and return its path.

    Closes the file descriptor immediately so the file can be opened
    by name in subsequent operations.
    """
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    return Path(tmp_path)

def remote_work_dir(identifier: str, *, is_windows: bool = False) -> str:
    """Build a temporary work directory path for a remote host."""
    short_id = identifier[:8]
    if is_windows:
        return f"C:\\Windows\\Temp\\.run-{short_id}"
    return f"/tmp/.run-{short_id}"
