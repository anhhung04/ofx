"""Project import handler."""

import json
import logging

import typer

from ofx.settings import settings

from ..encryption import save_encryption_key
from ..project_manager import ProjectManager

logger = logging.getLogger(settings.app_branding)

class ImportHandler:
    """Handles project import by cloning from git repository."""

    def __init__(self, url: str, name: str):
        self.url = url
        self.name = name
        self.project_path = ProjectManager._get_default_path() / name

    def run(self) -> None:
        """Import project by cloning from git repository."""
        if self.project_path.exists():
            raise FileExistsError(
                f"Project '{self.name}' already exists at {self.project_path}"
            )

        self.project_path.mkdir(parents=True, exist_ok=True)

        try:
            self._clone_repository()
            self._handle_encryption_setup()
            self._setup_project_config()

            logger.info(f"Successfully imported project '{self.name}' from {self.url}")

        except Exception as e:
            if self.project_path.exists():
                import shutil

                shutil.rmtree(self.project_path)
            raise RuntimeError(f"Failed to import project: {e}") from e

    def _clone_repository(self) -> None:
        """Clone the git repository."""
        import git

        logger.info(f"Cloning {self.url} to {self.project_path}")

        try:
            git.Repo.clone_from(self.url, self.project_path)
            logger.info("Repository cloned successfully")
        except git.GitCommandError as e:
            raise RuntimeError(f"Failed to clone repository: {e}") from e

    def _handle_encryption_setup(self) -> None:
        """Check for encryption configuration and set up if needed."""
        config_file = self.project_path / ".ofx-remote.json"

        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())

                if config.get("encrypt"):
                    logger.info("Project has encryption enabled")

                    key_file = self.project_path / ".ofx-encryption-key"
                    if not key_file.exists():
                        encryption_key = typer.prompt(
                            f"Enter encryption key for project '{self.name}'",
                            hide_input=True,
                        )
                        save_encryption_key(self.project_path, encryption_key)

            except Exception as e:
                logger.warning(f"Failed to process encryption config: {e}")

    def _setup_project_config(self) -> None:
        """Set up OFX project configuration if not already present."""
        config_file = self.project_path / ".ofx-remote.json"

        if not config_file.exists():
            config = {
                "type": "git",
                "config": {"url": self.url, "branch": "main"},
                "encrypt": False,
            }
            config_file.write_text(json.dumps(config, indent=2))
            logger.info("Created OFX project configuration")
