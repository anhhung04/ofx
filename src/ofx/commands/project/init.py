import json
import logging
from pathlib import Path
from typing import Any

from ofx.settings import get_console, settings

logger = logging.getLogger(settings.app_branding)
console = get_console()

ENGAGEMENT_FILE_STRUCTURE = [
    ("evidence", ["creds", "data", "screenshots"]),
    "logs",
    "scans",
    "scope",
    "tools",
    "exploits",
    "post-exploits",
]
DIRECTORY_STRUCTURE: list[str | tuple[str, list]] = [
    ("ept", ENGAGEMENT_FILE_STRUCTURE),
    ("ipt", ENGAGEMENT_FILE_STRUCTURE + ["lateral-movement"]),
]


class InitHandler:
    def __init__(
        self,
        base: str,
        is_multiphase: bool,
        remote_type: str = "",
        remote_config: dict[str, Any] | None = None,
        encrypt: bool = False,
        encryption_key: str = "",
    ):
        self._base_path = Path(base)
        self._is_multiphase = is_multiphase
        self._remote_type = remote_type
        self._remote_config = remote_config or {}
        self._encrypt = encrypt
        self._encryption_key = encryption_key

    def run(self):
        if self._is_multiphase:
            console.print(
                f"✅ Initializing multi-phase project at: {self._base_path.absolute()}"
            )
            self._make_dir(self._base_path, DIRECTORY_STRUCTURE)
        else:
            console.print(
                f"✅ Initializing single-phase project at: {self._base_path.absolute()}"
            )
            self._make_dir(self._base_path, ENGAGEMENT_FILE_STRUCTURE)

        if self._remote_type:
            self._setup_remote_storage()

        console.print("✅ Project initialization complete.")

    def _setup_remote_storage(self) -> None:
        """Setup remote storage based on type."""
        if self._remote_type == "git":
            self._setup_git()
        elif self._remote_type == "ssh":
            self._setup_ssh()
        elif self._remote_type == "s3":
            self._setup_s3()
        elif self._remote_type == "webdav":
            self._setup_webdav()

    def _setup_git(self) -> None:
        """Setup git remote for existing repository."""
        import git
        git_url = self._remote_config.get("url")
        branch = self._remote_config.get("branch", "main")

        if not git_url:
            console.print("⚠️ Git URL not provided, skipping git remote setup.")
            return

        if self._encrypt:
            config_file = self._base_path / ".ofx-remote.json"
            config = {
                "type": "git",
                "config": self._remote_config,
                "encrypt": True,
            }

            if self._encryption_key:
                import hashlib

                key_hash = hashlib.sha256(self._encryption_key.encode()).hexdigest()[
                    :16
                ]
                config["encryption_key_hash"] = key_hash

                key_file = self._base_path / ".ofx-encryption-key"
                key_file.write_text(self._encryption_key)
                key_file.chmod(0o600)
                logger.info(f"Encryption key saved to {key_file} (keep this secure!)")

                gitignore = self._base_path / ".gitignore"
                if gitignore.exists():
                    content = gitignore.read_text()
                    if ".ofx-encryption-key" not in content:
                        gitignore.write_text(content + "\n.ofx-encryption-key\n")

            config_file.write_text(json.dumps(config, indent=2))
            logger.info("Git storage configuration with encryption saved")

        try:
            repo = git.Repo(self._base_path)

            if not repo.remotes:
                origin = repo.create_remote("origin", git_url)
            else:
                origin = repo.remotes.origin
                origin.set_url(git_url)

            logger.info(f"Git remote configured: {origin}")

            if not repo.head.is_valid():
                repo.index.add(repo.untracked_files or [".gitignore"])
                repo.index.commit("Initial project structure")

            try:
                origin.push(refspec=f"{branch}:{branch}", set_upstream=True)
                console.print("✅ Pushed initial commit to remote repository.")
            except Exception as e:
                console.print(f"⚠️ Could not push to remote: {e}")
                console.print("You may need to push manually later.")

        except Exception as e:
            console.print(f"❌ Failed to setup Git remote: {e}")

    def _setup_ssh(self) -> None:
        """Setup SSH storage configuration."""
        config_file = self._base_path / ".ofx-remote.json"
        config = {
            "type": "ssh",
            "config": self._remote_config,
            "encrypt": self._encrypt,
        }

        if self._encrypt and self._encryption_key:
            import hashlib

            key_hash = hashlib.sha256(self._encryption_key.encode()).hexdigest()[:16]
            config["encryption_key_hash"] = key_hash

            key_file = self._base_path / ".ofx-encryption-key"
            key_file.write_text(self._encryption_key)
            key_file.chmod(0o600)
            logger.info(f"Encryption key saved to {key_file} (keep this secure!)")

            gitignore = self._base_path / ".gitignore"
            if gitignore.exists():
                content = gitignore.read_text()
                if ".ofx-encryption-key" not in content:
                    gitignore.write_text(content + "\n.ofx-encryption-key\n")

        config_file.write_text(json.dumps(config, indent=2))
        logger.info(f"SSH storage configuration saved to {config_file}")

        from .storage import SSHHandler

        SSHHandler(self._remote_config)
        logger.info("SSH key setup complete")

    def _setup_s3(self) -> None:
        """Setup S3 storage configuration."""
        config_file = self._base_path / ".ofx-remote.json"
        config = {
            "type": "s3",
            "config": self._remote_config,
            "encrypt": self._encrypt,
        }
        if self._encrypt and self._encryption_key:
            import hashlib

            key_hash = hashlib.sha256(self._encryption_key.encode()).hexdigest()[:16]
            config["encryption_key_hash"] = key_hash

            key_file = self._base_path / ".ofx-encryption-key"
            key_file.write_text(self._encryption_key)
            key_file.chmod(0o600)
            logger.info(f"Encryption key saved to {key_file} (keep this secure!)")

            gitignore = self._base_path / ".gitignore"
            if gitignore.exists():
                content = gitignore.read_text()
                if ".ofx-encryption-key" not in content:
                    gitignore.write_text(content + "\n.ofx-encryption-key\n")

        config_file.write_text(json.dumps(config, indent=2))
        logger.info(f"S3 storage configuration saved to {config_file}")
        logger.info("S3 will sync git repository using bundle files")

    def _setup_webdav(self) -> None:
        """Setup WebDAV storage configuration."""
        config_file = self._base_path / ".ofx-remote.json"
        config = {
            "type": "webdav",
            "config": self._remote_config,
            "encrypt": self._encrypt,
        }
        if self._encrypt and self._encryption_key:
            import hashlib

            key_hash = hashlib.sha256(self._encryption_key.encode()).hexdigest()[:16]
            config["encryption_key_hash"] = key_hash

            key_file = self._base_path / ".ofx-encryption-key"
            key_file.write_text(self._encryption_key)
            key_file.chmod(0o600)
            logger.info(f"Encryption key saved to {key_file} (keep this secure!)")

            gitignore = self._base_path / ".gitignore"
            if gitignore.exists():
                content = gitignore.read_text()
                if ".ofx-encryption-key" not in content:
                    gitignore.write_text(content + "\n.ofx-encryption-key\n")

        config_file.write_text(json.dumps(config, indent=2))
        logger.info(f"WebDAV storage configuration saved to {config_file}")
        logger.info("WebDAV will sync git repository using bundle files")

    def _make_dir(self, base: Path, items: list[str | tuple[str, list]]) -> None:
        base.mkdir(parents=True, exist_ok=True)
        for item in items:
            if not isinstance(item, str):
                self._make_dir(base / item[0], item[1])
            else:
                dir = base / item
                dir.mkdir(parents=True, exist_ok=True)
                (dir / ".gitkeep").touch()

        gitignore = base / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                ".ofx-remote.json\n.ofx-encryption-key\n__pycache__/\n*.pyc\n*.enc\n"
            )
