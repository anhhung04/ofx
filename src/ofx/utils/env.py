"""Environment utilities for OFX framework."""

import os
from pathlib import Path

from ofx.settings import TOOLS_BIN_DIR

_TOOLS_BIN_PATH = TOOLS_BIN_DIR.absolute().as_posix()


def populate_env(alt_env=None) -> dict[str, str]:
    """Populate environment variables including tools bin directory.

    Optimized to cache and reuse paths.
    """
    if alt_env is None:
        alt_env = {}

    envs = os.environ.copy()
    current_path = envs.get("PATH", "")
    if _TOOLS_BIN_PATH not in current_path:
        envs["PATH"] = f"{_TOOLS_BIN_PATH}{os.pathsep}{current_path}"
    envs["UV_TOOL_BIN_DIR"] = _TOOLS_BIN_PATH
    envs.update(alt_env)
    return envs
