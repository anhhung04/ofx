"""Project initialization handler."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import typer

from ofx.settings import get_console, settings

from ..encryption import (
    ensure_key_in_gitignore,
    generate_encryption_key,
    save_encryption_key,
)

logger = logging.getLogger(settings.app_branding)


class InitConfig:
    """Configuration for project initialization."""

    def __init__(
        self,
        base_path: Path,
        remote_type: str = "",
        remote_config: dict[str, Any] | None = None,
        encrypt: bool = False,
        encryption_key: str = "",
    ):
        self.base_path = base_path
        self.remote_type = remote_type
        self.remote_config = remote_config or {}
        self.encrypt = encrypt
        self.encryption_key = encryption_key


class InitHandler:
    """Handles project initialization."""

    def __init__(self, config: InitConfig):
        self._config = config

    @classmethod
    def run_interactive(cls, base_path: Path) -> None:
        """Run initialization with interactive prompts."""
        console = get_console()
        remote_type = "git"
        remote_config: dict[str, Any] = {"url": "", "branch": "main"}
        encrypt = False
        encryption_key = ""

        console.print("\n[bold]Initializing local git repository...[/]")

        console.print("\n[bold]Remote Storage Setup (Optional)[/]")
        setup_remote = typer.confirm(
            "Would you like to set up remote storage?", default=False
        )

        if setup_remote:
            console.print("\n[cyan]Available storage types:[/] git")
            storage_type = typer.prompt("Select remote storage type", default="git")

            if storage_type not in ["git"]:
                console.print(f"[red]Invalid storage type: {storage_type}[/]")
            elif storage_type == "git":
                git_url = typer.prompt("Enter Git repository URL")
                remote_config = {"url": git_url, "branch": "main"}

                console.print("\n[bold]Encryption Setup[/]")
                encrypt = typer.confirm(
                    "Enable encryption for files in git repository?", default=False
                )
                if encrypt:
                    encryption_key = typer.prompt(
                        "Enter encryption key (or press Enter to generate one)",
                        default="",
                        show_default=False,
                    )
                    if not encryption_key:
                        encryption_key = generate_encryption_key()
                        console.print(
                            f"\n[yellow]Generated encryption key:[/] {encryption_key}"
                        )
                        console.print(
                            "[yellow]⚠️  Save this key securely! You'll need it to decrypt files.[/]"
                        )

        config = InitConfig(
            base_path=base_path,
            remote_type=remote_type,
            remote_config=remote_config,
            encrypt=encrypt,
            encryption_key=encryption_key,
        )

        console.print("[bold green]Initializing project...[/bold green]")
        cls(config).run()

    def run(self) -> None:
        """Configure Git and optional remote storage."""
        console = get_console()
        cfg = self._config

        console.print(f"✅ Initializing project at: {cfg.base_path.absolute()}")
        self._setup_local_git()

        if cfg.remote_type and cfg.remote_config.get("url"):
            self._setup_remote_storage()

        console.print("✅ Project initialization complete.")

    def _setup_local_git(self) -> None:
        """Initialize local git repository."""
        import git

        console = get_console()
        try:
            try:
                repo = git.Repo(self._config.base_path)
                logger.info(
                    f"Using existing git repository at {self._config.base_path}"
                )
            except Exception:
                repo = git.Repo.init(self._config.base_path)
                logger.info(f"Initialized git repository at {self._config.base_path}")

            if not repo.head.is_valid():
                repo.index.add(repo.untracked_files or [".gitignore"])
                repo.index.commit("Initial project structure")
                logger.info("Created initial commit")
                console.print("✅ Local git repository initialized.")
        except Exception as e:
            console.print(f"⚠️ Failed to initialize git repository: {e}")

    def _setup_remote_storage(self) -> None:
        """Setup remote storage based on type."""
        if self._config.remote_type == "git":
            self._setup_git_remote()

    def _setup_git_remote(self) -> None:
        """Setup git remote for existing repository."""
        import git

        console = get_console()
        cfg = self._config
        git_url = cfg.remote_config.get("url")
        branch = cfg.remote_config.get("branch", "main")

        if not git_url:
            console.print("⚠️ Git URL not provided, skipping git remote setup.")
            return

        if cfg.encrypt:
            self._setup_encryption_config()

        try:
            repo = git.Repo(cfg.base_path)

            if not repo.remotes:
                origin = repo.create_remote("origin", git_url)
            else:
                origin = repo.remotes.origin
                origin.set_url(git_url)

            logger.info(f"Git remote configured: {origin}")

            try:
                origin.push(refspec=f"{branch}:{branch}", set_upstream=True)
                console.print("✅ Pushed to remote repository.")
            except Exception as e:
                console.print(f"⚠️ Could not push to remote: {e}")
                console.print("You may need to push manually later.")

        except Exception as e:
            console.print(f"❌ Failed to setup Git remote: {e}")

    def _setup_encryption_config(self) -> None:
        """Setup encryption configuration for the project."""
        cfg = self._config
        config_file = cfg.base_path / ".ofx-remote.json"

        config: dict[str, Any] = {
            "type": "git",
            "config": cfg.remote_config,
            "encrypt": True,
        }

        if cfg.encryption_key:
            key_hash = hashlib.sha256(cfg.encryption_key.encode()).hexdigest()[:16]
            config["encryption_key_hash"] = key_hash

            save_encryption_key(cfg.base_path, cfg.encryption_key)
            ensure_key_in_gitignore(cfg.base_path)

        config_file.write_text(json.dumps(config, indent=2))
        logger.info("Git storage configuration with encryption saved")

    def _make_dir(self, base: Path, items: list[str | tuple[str, list]]) -> None:
        """Recursively create directory structure."""
        base.mkdir(parents=True, exist_ok=True)

        for item in items:
            if not isinstance(item, str):
                self._make_dir(base / item[0], item[1])
            else:
                dir_path = base / item
                dir_path.mkdir(parents=True, exist_ok=True)
                (dir_path / ".gitkeep").touch()

        gitignore = base / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                ".ofx-remote.json\n.ofx-encryption-key\n__pycache__/\n*.pyc\n*.enc\n"
            )
