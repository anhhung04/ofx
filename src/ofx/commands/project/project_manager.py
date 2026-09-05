import logging
import shutil
from datetime import UTC, datetime
from os import getenv
from pathlib import Path

from ofx.settings import DEFAULT_PROJECTS_PATH

logger = logging.getLogger("ofx")

# Standard project workspace directories
PROJECT_DIRS = ["evidence", "notes", "workflows", "runs"]

PROJECT_GITIGNORE = """# OFX Project
.ofx-encryption-key
*.enc

# Outputs
runs/

# Secrets
*.kdbx
*.key

# OS files
.DS_Store
Thumbs.db
"""

PROJECT_README = """# {name}

## Authorization and Rules of Engagement

- **Client:**
- **Authorized scope:**
- **Out of scope:**
- **Rules of engagement:**
- **Start date:** {date}
- **Status:** Active

## Notes

Keep scope, RoE, targets, decisions, and engagement notes in this file.

## Quick Start

```bash
# Run built-in recon workflow
ofx flow run external-recon --input target=example.com

# Run custom workflow
ofx flow run workflows/my-scan.yml
```

## Structure

| Path | Purpose |
|---|---|
| `README.md` | Authorization, scope, RoE, targets, and notes |
| `evidence/` | Evidence and collected files |
| `notes/` | Human-authored asset and engagement notes |
| `workflows/` | Workspace-local OFX workflows |
| `runs/` | Generated workflow output (ignored by Git) |
"""


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
        """Resolve project path from name, relative, or absolute path."""
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
        """Create a new engagement workspace with standard directory structure."""
        import git

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        project_path = cls._get_default_path() / safe_name
        project_path.mkdir(parents=True, exist_ok=True)

        # Create standard workspace directories
        for dir_name in PROJECT_DIRS:
            (project_path / dir_name).mkdir(exist_ok=True)

        # Create README
        readme = project_path / "README.md"
        if not readme.exists():
            readme.write_text(
                PROJECT_README.format(
                    name=safe_name,
                    date=datetime.now(UTC).strftime("%Y-%m-%d"),
                )
            )

        # Create .gitignore
        gitignore = project_path / ".gitignore"
        gitignore.write_text(PROJECT_GITIGNORE)

        # Init git repo
        try:
            git.Repo.init(str(project_path), initial_branch="main")
        except Exception as e:
            logger.debug("Failed to init git repo for project '%s': %s", safe_name, e)

        logger.info("Created project workspace: %s", project_path)
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
        """Return the active project Path as resolved from settings."""
        from ofx.settings import settings

        name = getattr(settings, "active_project", None)
        if name:
            try:
                return Path(cls.resolve_path(name))
            except Exception as e:
                logger.debug("Failed to resolve active project '%s': %s", name, e)
        return None

    @classmethod
    def get_run_dir(cls, workflow_name: str) -> Path | None:
        """Get the run output directory for a workflow within the active project.

        Creates: <project>/runs/<YYYY-MM-DD>_<workflow>/
        """
        active = cls.get_active_path()
        if active is None:
            return None
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        run_dir = active / "runs" / f"{date_str}_{workflow_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    @classmethod
    def get_project_workflow_dir(cls) -> Path | None:
        """Get the workflows directory within the active project."""
        active = cls.get_active_path()
        if active is None:
            return None
        workflows_dir = active / "workflows"
        workflows_dir.mkdir(exist_ok=True)
        return workflows_dir
