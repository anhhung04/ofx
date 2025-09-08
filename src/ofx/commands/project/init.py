import git
import logging

from pathlib import Path
from typing import List, Tuple
from ofx.utils.misc import MetaSingleton
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

ENGAGEMENT_FILE_STRUCTURE = [
    ("evidence", ["creds", "data", "screenshots"]),
    "logs",
    "scans",
    "scope",
    "tools",
    "exploits",
    "post-exploits",
]
DIRECTORY_STRUCTURE: List[str | Tuple[str, List]] = [
    ("ept", ENGAGEMENT_FILE_STRUCTURE),
    ("ipt", ENGAGEMENT_FILE_STRUCTURE + ["lateral-movement"]),
]


class InitHandler(metaclass=MetaSingleton):
    def __init__(self, base: str, is_multiphase: bool, git_url: str | None):
        self._base_path = Path(base)
        self._is_multiphase = is_multiphase
        self._git_url = git_url

    def run(self):
        if self._is_multiphase:
            logger.info(
                f"Initializing multi-phase project at: {self._base_path.absolute()}"
            )
            self._make_dir(self._base_path, DIRECTORY_STRUCTURE)
        else:
            logger.info(
                f"Initializing single-phase project at: {self._base_path.absolute()}"
            )
            self._make_dir(self._base_path, ENGAGEMENT_FILE_STRUCTURE)
        if self._git_url:
            try:
                repo = git.Repo.init(self._base_path, initial_branch="main")
                origin = repo.create_remote("origin", self._git_url)
                logger.info(f"Initialized empty Git repository and linked to {origin}")
                repo.index.add(repo.untracked_files)
                repo.index.commit("Initial structure")
                origin.push(refspec="main:main", set_upstream=True)
                logger.info("Pushed initial commit to remote repository.")
            except Exception as e:
                logger.error(f"Failed to initialize Git repository: {e}")
        logger.info("Project initialization complete.")

    def _make_dir(self, base: Path, items: List[str | Tuple[str, List]]) -> None:
        base.mkdir(parents=True, exist_ok=True)
        for item in items:
            if not isinstance(item, str):
                self._make_dir(base / item[0], item[1])
            else:
                dir = base / item
                dir.mkdir(parents=True, exist_ok=True)
                (dir / ".gitkeep").touch()
