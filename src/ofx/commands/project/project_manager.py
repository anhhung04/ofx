import logging
import shutil
from os import getenv
from pathlib import Path

from ofx.settings import DEFAULT_PROJECTS_PATH

logger = logging.getLogger("ofx")


class ProjectManager:
    @classmethod
    def _get_default_path(cls) -> Path:
        """Get default project path as Path object."""
        path = getenv("OFX_PROJECTS_PATH", DEFAULT_PROJECTS_PATH)
        if isinstance(path, Path):
            return path
        return Path(path)

    @classmethod
    def resolve_path(cls, project_arg: str | None) -> str:
        """Resolve project path from name, relative, or absolute path.
        Raises ValueError if project_arg is None.
        """
        if project_arg is None:
            raise ValueError("project_arg cannot be None")
        project_path = Path(project_arg)

        if project_path.is_absolute():
            return str(project_path.resolve())

        candidate = cls._get_default_path() / project_arg
        if candidate.exists():
            return str(candidate)

        rel_path = Path.cwd() / project_arg
        if rel_path.exists():
            return str(rel_path.resolve())

        return str(candidate)

    @classmethod
    def list_projects(cls) -> list[str]:
        """List all projects in the default project path."""
        default_path = cls._get_default_path()
        if not default_path.exists():
            return []
        return [
            item.name
            for item in default_path.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ]

    @classmethod
    def create_project(cls, name: str) -> str:
        """Create a new project directory with auto-initialized git repo."""
        import git

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        project_path = cls._get_default_path() / safe_name
        project_path.mkdir(parents=True, exist_ok=True)

        try:
            git.Repo.init(str(project_path), initial_branch="main")
            gitignore_path = project_path / ".gitignore"
            gitignore_path.write_text(".ofx-encryption-key\n*.enc\n")
        except Exception as e:
            logger.debug("Failed to init git repo for project '%s': %s", safe_name, e)
            pass

        return str(project_path)

    @classmethod
    def delete_project(cls, name: str) -> bool:
        """Delete a project by name."""
        project_path = cls._get_default_path() / name
        if project_path.exists() and project_path.is_dir():
            shutil.rmtree(project_path)
            return True
        return False

    @classmethod
    def get_active_path(cls) -> Path | None:
        """Return the active project Path as resolved from settings (config.yml / env var).

        Priority is handled by pydantic-settings source order:
        env var OFX_ACTIVE_PROJECT > config.yml active_project.
        """
        from ofx.settings import settings

        name = getattr(settings, "active_project", None)
        if name:
            try:
                return Path(cls.resolve_path(name))
            except Exception as e:
                logger.debug("Failed to resolve active project '%s': %s", name, e)
        return None
