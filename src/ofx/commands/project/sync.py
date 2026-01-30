import json
import logging
import os
from datetime import datetime
from pathlib import Path

import typer

from ofx.settings import settings

from .storage import EncryptionHandler, GitHandler, SSHHandler

logger = logging.getLogger(settings.app_branding)


class SyncProjectHandler:
    def __init__(
        self,
        path: str,
        remote_type: str = "git",
        remote_config: str = "",
        encrypt: bool = False,
        encryption_key: str = "",
        message: str = "",
    ):
        self._project_path = Path(path)
        self._remote_type = remote_type
        self._remote_config = remote_config
        self._encrypt = encrypt
        self._encryption_key = encryption_key or os.getenv("OFX_ENCRYPTION_KEY")
        self._message = message

        self._load_project_config()

        if self._encrypt and not self._encryption_key:
            self._encryption_key = typer.prompt(
                "Enter encryption key for syncing project", hide_input=True
            )

    def _load_project_config(self) -> None:
        """Load project configuration from .ofx-remote.json."""
        config_file = self._project_path / ".ofx-remote.json"
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())

                if not self._remote_config:
                    self._remote_type = config.get("type", self._remote_type)
                    self._remote_config = json.dumps(config.get("config", {}))

                if config.get("encrypt") and not self._encrypt:
                    self._encrypt = True
                    logger.info("Encryption enabled from project configuration")

                if self._encrypt and not self._encryption_key:
                    key_file = self._project_path / ".ofx-encryption-key"
                    if key_file.exists():
                        self._encryption_key = key_file.read_text().strip()
                        logger.info("Loaded encryption key from project configuration")
                    else:
                        logger.warning("Encryption enabled but key file not found")

            except Exception as e:
                logger.warning(f"Failed to load project configuration: {e}")

    def run(self):
        if not self._project_path.exists():
            raise FileNotFoundError(
                f"Project path {self._project_path} does not exist."
            )
        if not self._project_path.is_dir():
            raise NotADirectoryError(f"Project path {self._project_path} is not a dir.")

        logger.info(f"Syncing project at: {self._project_path.absolute()}")
        logger.info(f"Remote storage type: {self._remote_type}")

        self._auto_commit()

        if self._remote_type == "git":
            self._sync_git()
        elif self._remote_type == "ssh":
            self._sync_ssh()
        else:
            logger.warning(f"Unknown remote type: {self._remote_type}")
            raise ValueError(f"Unsupported remote type: {self._remote_type}")

    def _auto_commit(self) -> None:
        """Auto-commit changes before sync with timestamp."""
        try:
            import git

            repo = git.Repo(self._project_path)

            if repo.is_dirty() or repo.untracked_files:
                repo.index.add(repo.untracked_files)
                repo.git.add(A=True)

                if self._message:
                    commit_msg = self._message
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    hostname = os.getenv("HOSTNAME", "unknown")
                    user = os.getenv("USER", "unknown")
                    commit_msg = f"Auto-sync: {timestamp} by {user}@{hostname}"

                repo.index.commit(commit_msg)
                logger.info(f"Auto-committed changes: {commit_msg}")
            else:
                logger.info("No changes to commit")
        except Exception as e:
            logger.warning(f"Auto-commit skipped: {e}")

    def _sync_git(self) -> None:
        """Sync with git remote."""
        config = json.loads(self._remote_config) if self._remote_config else {}
        handler = GitHandler(
            str(self._project_path),
            config,
            encrypt=self._encrypt,
            encryption_key=self._encryption_key,
        )
        try:
            handler.sync()
            logger.info("Successfully synced with git remote.")
        except Exception as e:
            logger.error(f"Git sync failed: {e}")
            raise

    def _sync_ssh(self) -> None:
        """Sync with SSH remote."""
        config = json.loads(self._remote_config) if self._remote_config else {}
        handler = SSHHandler(
            config,
        )
        try:
            handler.sync(self._project_path)
            logger.info("Successfully synced with SSH remote.")
        except Exception as e:
            logger.error(f"SSH sync failed: {e}")
            raise

    def _encrypt_local_files(self, encryptor: EncryptionHandler) -> None:
        """Encrypt files locally before syncing."""
        for root, _, files in os.walk(self._project_path):
            if ".git" in root:
                continue

            for file in files:
                if file.endswith(".enc") or file in [
                    ".ofx-remote.json",
                    ".ofx-encryption-key",
                    ".gitignore",
                ]:
                    continue

                file_path = os.path.join(root, file)
                encrypted_file_path = f"{file_path}.enc"

                if not os.path.exists(encrypted_file_path) or os.path.getmtime(
                    file_path
                ) > os.path.getmtime(encrypted_file_path):
                    try:
                        encrypted_data = encryptor.encrypt_file(file_path)
                        with open(encrypted_file_path, "wb") as ef:
                            ef.write(encrypted_data)
                        logger.debug(f"Encrypted: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to encrypt {file_path}: {e}")

    def _upload_files(self, handler, encryptor=None) -> None:
        """Upload all project files using the given handler."""
        for root, _, files in os.walk(self._project_path):
            for f in files:
                if ".git" in root or f == ".ofx-remote.json":
                    continue
                local_path = os.path.join(root, f)
                remote_path = os.path.relpath(local_path, self._project_path)

                try:
                    if encryptor:
                        encrypted_data = encryptor.encrypt_file(local_path)
                        temp_file = f"{local_path}.enc"
                        with open(temp_file, "wb") as tf:
                            tf.write(encrypted_data)
                        handler.upload(temp_file, f"{remote_path}.enc")
                        os.remove(temp_file)
                        logger.debug(f"Encrypted and uploaded: {remote_path}")
                    else:
                        handler.upload(local_path, remote_path)
                except Exception as e:
                    logger.warning(f"Failed to upload {local_path}: {e}")

    @property
    def encryption_key(self) -> str:
        if not self._encryption_key:
            raise ValueError(
                "Encryption key is not set. "
                "Use --encryption-key or set OFX_ENCRYPTION_KEY environment variable."
            )
        return self._encryption_key
