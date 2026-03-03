"""Storage handlers for remote synchronization.

Cross-platform: prefers ``paramiko`` (pure-Python SSH) when available,
falls back to system ``ssh``/``rsync``/``scp`` on Linux/macOS.
SSH key generation uses the ``cryptography`` library (always available).
"""

from __future__ import annotations

import getpass
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ofx.commands.project.encryption import EncryptionHandler
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

# ---------------------------------------------------------------------------
# Optional paramiko import
# ---------------------------------------------------------------------------

try:
    import paramiko  # type: ignore[import-untyped]

    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


def _is_windows() -> bool:
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# SSH key helpers (pure-Python via ``cryptography``)
# ---------------------------------------------------------------------------


def _generate_ssh_keypair(key_path: Path) -> str:
    """Generate an RSA-4096 SSH key pair using the ``cryptography`` library.

    Returns:
        The public key in OpenSSH format.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(pem)
    key_path.chmod(0o600)

    pub = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    pub_text = pub.decode() + " ofx-project-sync"
    pub_path = Path(str(key_path) + ".pub")
    pub_path.write_text(pub_text + "\n")
    return pub_text


# ---------------------------------------------------------------------------
# Paramiko-based SSH handler
# ---------------------------------------------------------------------------


class _ParamikoSSH:
    """Pure-Python SSH operations via ``paramiko``."""

    def __init__(self, host: str, user: str, port: int, key_path: Path):
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path
        self._client: paramiko.SSHClient | None = None

    def _connect(self) -> paramiko.SSHClient:
        if self._client is not None:
            return self._client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            key_filename=str(self.key_path),
            timeout=30,
        )
        self._client = client
        return client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def exec_command(self, cmd: str) -> str:
        client = self._connect()
        _, stdout, stderr = client.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if exit_code != 0:
            raise RuntimeError(f"Remote command failed ({exit_code}): {err}")
        return out

    def add_authorized_key(self, pub_key: str, password: str) -> None:
        """Connect with password and append *pub_key* to remote authorized_keys."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=password,
                timeout=30,
            )
            cmd = (
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                f"echo '{pub_key}' >> ~/.ssh/authorized_keys && "
                "chmod 600 ~/.ssh/authorized_keys"
            )
            _, stdout, stderr = client.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                raise RuntimeError(stderr.read().decode())
        finally:
            client.close()

    def sftp_sync(self, local_path: Path, remote_path: str) -> None:
        """Recursively upload *local_path* to *remote_path* via SFTP."""
        client = self._connect()
        sftp = client.open_sftp()
        try:
            self._ensure_remote_dir(sftp, remote_path)
            self._upload_tree(sftp, local_path, remote_path)
        finally:
            sftp.close()

    def sftp_upload(self, local_file: str, remote_file: str) -> None:
        """Upload a single file via SFTP."""
        client = self._connect()
        sftp = client.open_sftp()
        try:
            remote_dir = os.path.dirname(remote_file)
            if remote_dir:
                self._ensure_remote_dir(sftp, remote_dir)
            sftp.put(local_file, remote_file)
        finally:
            sftp.close()

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str) -> None:  # type: ignore[name-defined]
        parts = path.replace("\\", "/").split("/")
        current = ""
        for part in parts:
            if not part:
                current = "/"
                continue
            current = f"{current}/{part}" if current else part
            if current == "/":
                continue
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

    @staticmethod
    def _upload_tree(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:  # type: ignore[name-defined]
        for item in local.iterdir():
            remote_item = f"{remote}/{item.name}"
            if item.is_dir():
                try:
                    sftp.stat(remote_item)
                except FileNotFoundError:
                    sftp.mkdir(remote_item)
                _ParamikoSSH._upload_tree(sftp, item, remote_item)
            else:
                sftp.put(str(item), remote_item)


# ---------------------------------------------------------------------------
# SSHHandler — cross-platform
# ---------------------------------------------------------------------------


class SSHHandler:
    """Handles SSH/rsync-based remote synchronization.

    Uses ``paramiko`` (pure Python) when available, falling back to
    system ``ssh``/``rsync``/``scp`` on Linux/macOS.
    """

    def __init__(self, config: dict):
        self.host = config.get("host")
        self.user = config.get("user")
        self.remote_path = config.get("remote_path")
        self.port = config.get("port", 22)
        self.key_path = self._find_ssh_key()
        self._ensure_ssh_key()

    def _find_ssh_key(self) -> Path:
        """Find existing SSH key or return default path."""
        ssh_dir = Path.home() / ".ssh"
        common_keys = ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]
        for key_name in common_keys:
            key_path = ssh_dir / key_name
            if key_path.exists():
                return key_path
        return ssh_dir / "ofx_id_rsa"

    def _ensure_ssh_key(self) -> None:
        """Ensure SSH key exists; generate with ``cryptography`` if needed."""
        if self.key_path.exists():
            return

        logger.info("Generating SSH key at %s (pure-Python)", self.key_path)
        pub_key = _generate_ssh_keypair(self.key_path)

        logger.info("SSH key generated. Attempting to add public key to remote server...")
        try:
            self._add_key_to_remote(pub_key)
            logger.info("Public key successfully added to remote server")
        except Exception as exc:
            logger.warning("Could not automatically add key to remote: %s", exc)
            logger.info("Please manually add this public key to your remote server:")
            logger.info("\n%s\n", pub_key)
            logger.info(
                "Run on remote: echo '%s' >> ~/.ssh/authorized_keys", pub_key
            )

    def _add_key_to_remote(self, pub_key: str) -> None:
        """Add public key to remote server, prompting for a password."""
        password = getpass.getpass(
            f"Enter password for {self.user}@{self.host} to add SSH key: "
        )

        if HAS_PARAMIKO:
            _ParamikoSSH(
                self.host, self.user, self.port, self.key_path
            ).add_authorized_key(pub_key, password)
            return

        # Fallback: system commands (Linux/macOS only)
        if _is_windows():
            raise RuntimeError(
                "paramiko is required for SSH key deployment on Windows. "
                "Install it with: pip install ofx[ssh]"
            )

        try:
            subprocess.run(
                [
                    "sshpass", "-p", password,
                    "ssh-copy-id",
                    "-i", str(self.key_path),
                    "-p", str(self.port),
                    "-o", "StrictHostKeyChecking=no",
                    f"{self.user}@{self.host}",
                ],
                check=True, capture_output=True, text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            cmd = (
                "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
                f"echo '{pub_key}' >> ~/.ssh/authorized_keys && "
                "chmod 600 ~/.ssh/authorized_keys"
            )
            subprocess.run(
                [
                    "sshpass", "-p", password,
                    "ssh", "-p", str(self.port),
                    "-o", "StrictHostKeyChecking=no",
                    f"{self.user}@{self.host}", cmd,
                ],
                check=True, capture_output=True, text=True,
            )

    def sync(self, local_path: Path) -> None:
        """Sync local directory to remote."""
        if HAS_PARAMIKO:
            ssh = _ParamikoSSH(self.host, self.user, self.port, self.key_path)
            try:
                ssh.sftp_sync(local_path, self.remote_path)
                logger.info(
                    "Successfully synced to %s@%s:%s (paramiko/SFTP)",
                    self.user, self.host, self.remote_path,
                )
            finally:
                ssh.close()
            return

        if _is_windows():
            raise RuntimeError(
                "paramiko is required for SSH sync on Windows. "
                "Install it with: pip install ofx[ssh]"
            )

        # Fallback: rsync
        remote_uri = f"{self.user}@{self.host}:{self.remote_path}"
        try:
            result = subprocess.run(
                [
                    "rsync", "-avz", "--delete",
                    "-e",
                    f"ssh -i {self.key_path} -p {self.port} -o StrictHostKeyChecking=no",
                    f"{local_path}/",
                    remote_uri,
                ],
                check=True, capture_output=True, text=True,
            )
            logger.info("Successfully synced to %s (rsync)", remote_uri)
            if result.stdout:
                logger.debug(result.stdout)
        except FileNotFoundError:
            raise RuntimeError(
                "rsync is not installed. Install paramiko (pip install ofx[ssh]) "
                "for cross-platform support, or install rsync on your system."
            ) from None
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SSH sync failed: {e.stderr}") from e

    def upload(self, local_path: str, remote_path: str) -> None:
        """Upload a single file."""
        remote_file = f"{self.remote_path}/{remote_path}"

        if HAS_PARAMIKO:
            ssh = _ParamikoSSH(self.host, self.user, self.port, self.key_path)
            try:
                ssh.sftp_upload(local_path, remote_file)
            finally:
                ssh.close()
            return

        if _is_windows():
            raise RuntimeError(
                "paramiko is required for SCP uploads on Windows. "
                "Install it with: pip install ofx[ssh]"
            )

        # Fallback: scp
        remote_target = f"{self.user}@{self.host}:{remote_file}"
        try:
            subprocess.run(
                [
                    "scp",
                    "-i", str(self.key_path),
                    "-P", str(self.port),
                    "-o", "StrictHostKeyChecking=no",
                    local_path,
                    remote_target,
                ],
                check=True, capture_output=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "scp is not installed. Install paramiko (pip install ofx[ssh]) "
                "for cross-platform support."
            ) from None
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SCP upload failed: {e.stderr}") from e


class GitHandler:
    """Handles Git-based remote synchronization."""

    def __init__(
        self,
        project_path: str,
        config: dict | None = None,
        encrypt: bool = False,
        encryption_key: str | None = None,
    ):
        self.project_path = Path(project_path)
        self.config = config or {}
        self.branch = self.config.get("branch", "main")
        self.encrypt = encrypt
        self.encryption_key = encryption_key

        if self.encrypt and self.encryption_key:
            self.encryptor = EncryptionHandler(self.encryption_key)
        else:
            self.encryptor = None

    def sync(self) -> None:
        """Sync with git remote."""
        import git

        try:
            repo = git.Repo(self.project_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            raise RuntimeError(
                f"No git repository found at {self.project_path}. "
                "Initialize with 'ofx project init' or create project first."
            ) from None

        try:
            if self.encrypt and self.encryptor:
                self.encryptor.setup_git_filters(self.project_path)

            if not repo.remotes:
                remote_url = self.config.get("url")
                if remote_url:
                    repo.create_remote("origin", remote_url)
                else:
                    raise RuntimeError("No git remote configured. Add a remote URL in config.")

            origin = repo.remotes.origin

            has_local_changes = False
            if repo.untracked_files or repo.is_dirty():
                has_local_changes = True
                repo.index.add(repo.untracked_files)
                repo.git.add(A=True)

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                commit_msg = f"Auto-sync: {timestamp}"
                repo.index.commit(commit_msg)

            try:
                origin.fetch()
                if self.branch in [ref.name.split("/")[-1] for ref in origin.refs]:
                    repo.git.pull("origin", self.branch, rebase=True)
            except git.GitCommandError as e:
                if "couldn't find remote ref" not in str(e).lower():
                    raise

            if has_local_changes:
                origin.push(refspec=f"{self.branch}:{self.branch}", set_upstream=True)
            else:
                logger.info("No local changes to push")

        except Exception as e:
            raise RuntimeError(f"Git sync failed: {e}") from e
