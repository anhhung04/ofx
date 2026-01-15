"""Template helper functions for workflow template resolution"""

import os
import shutil
from pathlib import Path
from typing import Any, Callable

import aiofiles
import aiofiles.os as aio_os

from ofx.settings import TOOLS_BIN_DIR, TOOLS_DIR


async def _read_file(path: str) -> str | None:
    """Read file content asynchronously"""
    if await aio_os.path.exists(path):
        async with aiofiles.open(path) as f:
            return await f.read()
    return None


async def _write_file(path: str, content: str):
    """Write file content asynchronously"""
    async with aiofiles.open(path, 'w') as f:
        await f.write(content)


class TemplateHelpers:
    """Provides helper functions for Jinja2 template rendering in workflows"""

    _support_funcs_cache: dict[str, Any] | None = None

    @classmethod
    def get_support_functions(cls, workflow_dir: Path, envs: dict[str, str]) -> dict[str, Any]:
        """Get template support functions with caching
        
        Args:
            workflow_dir: Current workflow directory
            envs: Environment variables
            
        Returns:
            Dictionary of support functions available in templates
        """
        if cls._support_funcs_cache is None:
            sudo = "sudo" if os.geteuid() != 0 and shutil.which("sudo") else ""
            tools_dir_str = str(TOOLS_DIR.absolute())
            tools_bin_dir_str = str(TOOLS_BIN_DIR.absolute())
            
            cls._support_funcs_cache = {
                "sudo": sudo,
                "tools_dir": tools_dir_str,
                "tools_bin_dir": tools_bin_dir_str,
                "fapt": lambda app: f'if [ -z "$( ls -A /var/lib/apt/lists/ )" ]; then {sudo} apt-get update; fi && {sudo} apt-get install -y --no-install-recommends {app}',
                "uv_install": lambda name: f"uv tool install --python-preference managed --force --reinstall {name}",
                "go_install": lambda pkg: f"GO111MODULE=on GOBIN={tools_bin_dir_str} go install {pkg}@latest",
                "cargo_install": lambda name: f"cargo install --root {tools_dir_str} {name}",
                "npm_install": lambda name: f"npm install -g --prefix {tools_dir_str} {name}",
                "static_install": lambda url, name=None: (
                    f"curl -fSsL {url} -o {tools_bin_dir_str}/{name if name else Path(url).name} && chmod +x {tools_bin_dir_str}/{name if name else Path(url).name}"
                ),
                "file_read": _read_file,
                "file_write": _write_file,
                "file_exists": aio_os.path.exists,
                "python": __import__('sys').executable,
                "pip_install": lambda pkg: f'"{__import__("sys").executable}" -m pip install --upgrade {pkg}',
            }
        
        support_funcs = cls._support_funcs_cache.copy()
        support_funcs["workflow_dir"] = workflow_dir.absolute().as_posix()
        support_funcs["env"] = envs
        
        return support_funcs

    @classmethod
    def reset_cache(cls):
        """Reset the support functions cache (useful for testing)"""
        cls._support_funcs_cache = None
