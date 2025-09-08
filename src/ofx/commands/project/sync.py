import git
import logging

from datetime import datetime
from pathlib import Path
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)


class SyncProjectHandler:
    def __init__(self, path: str):
        self._project_path = Path(path)

    def run(self):
        if not self._project_path.exists():
            raise FileNotFoundError(
                f"Project path {self._project_path} does not exist."
            )
        if not self._project_path.is_dir():
            raise NotADirectoryError(f"Project path {self._project_path} is not a dir.")
        logger.info(f"Syncing project at: {self._project_path.absolute()}")
        repo = git.Repo(self._project_path)
        if repo.is_dirty(untracked_files=True):
            logger.warning(
                f"Project at {self._project_path} has uncommitted changes. Stashing them."
            )
            repo.git.stash("save", "wip-before-sync")
        origin = repo.remotes.origin
        origin.pull(refspec="main:main", rebase=True)
        logger.info(f"Successfully pulled latest changes from remote repository.")
        stash_list = repo.git.stash("list")
        if "wip-before-sync" in stash_list:
            stash_list = stash_list.split("\n")
            stash_line = next(s for s in stash_list if "wip-before-sync" in s)
            stash_index = stash_line.split(":")[0]
            repo.git.stash("pop", stash_index)
            logger.info("Re-applied stashed changes.")
        else:
            logger.info("No stashed changes to re-apply.")
        repo.index.add(repo.untracked_files)
        repo.index.commit(
            "Sync local changes at "
            + str(self._project_path)
            + " on "
            + datetime.now().isoformat()
        )
        origin.push(refspec="main:main")
        logger.info("Successfully pushed local changes to remote repository.")
