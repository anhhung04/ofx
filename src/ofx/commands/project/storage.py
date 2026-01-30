import getpass
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path


class SSHHandler:
    def __init__(self, config: dict):
        self.host = config.get("host")
        self.user = config.get("user")
        self.remote_path = config.get("remote_path")
        self.port = config.get("port", 22)
        self.key_path = self._find_ssh_key()
        self._ensure_ssh_key()

    def _find_ssh_key(self) -> Path:
        ssh_dir = Path.home() / ".ssh"
        common_keys = ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]

        for key_name in common_keys:
            key_path = ssh_dir / key_name
            if key_path.exists():
                return key_path

        return ssh_dir / "ofx_id_rsa"

    def _ensure_ssh_key(self) -> None:
        if not self.key_path.exists():
            logger = logging.getLogger("ofx")
            logger.info(f"Generating SSH key at {self.key_path}")

            subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "rsa",
                    "-b",
                    "4096",
                    "-f",
                    str(self.key_path),
                    "-N",
                    "",
                    "-C",
                    "ofx-project-sync",
                ],
                check=True,
                capture_output=True,
            )

            self.key_path.chmod(0o600)

            pub_key_path = Path(str(self.key_path) + ".pub")
            pub_key = pub_key_path.read_text().strip()

            logger.info(
                "SSH key generated. Attempting to add public key to remote server..."
            )

            try:
                self._add_key_to_remote(pub_key)
                logger.info("✓ Public key successfully added to remote server")
            except Exception as e:
                logger.warning(f"Could not automatically add key to remote: {e}")
                logger.info(
                    "Please manually add this public key to your remote server:"
                )
                logger.info(f"\n{pub_key}\n")
                logger.info(
                    f"Run on remote: echo '{pub_key}' >> ~/.ssh/authorized_keys"
                )

    def _add_key_to_remote(self, pub_key: str) -> None:
        password = getpass.getpass(
            f"Enter password for {self.user}@{self.host} to add SSH key: "
        )

        try:
            subprocess.run(
                [
                    "sshpass",
                    "-p",
                    password,
                    "ssh-copy-id",
                    "-i",
                    str(self.key_path),
                    "-p",
                    str(self.port),
                    "-o",
                    "StrictHostKeyChecking=no",
                    f"{self.user}@{self.host}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            cmd = f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '{pub_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

            subprocess.run(
                [
                    "sshpass",
                    "-p",
                    password,
                    "ssh",
                    "-p",
                    str(self.port),
                    "-o",
                    "StrictHostKeyChecking=no",
                    f"{self.user}@{self.host}",
                    cmd,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    def sync(self, local_path: Path) -> None:
        logger = logging.getLogger("ofx")
        remote_uri = f"{self.user}@{self.host}:{self.remote_path}"

        try:
            result = subprocess.run(
                [
                    "rsync",
                    "-avz",
                    "--delete",
                    "-e",
                    f"ssh -i {self.key_path} -p {self.port} -o StrictHostKeyChecking=no",
                    f"{local_path}/",
                    remote_uri,
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            logger.info(f"Successfully synced to {remote_uri}")
            if result.stdout:
                logger.debug(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SSH sync failed: {e.stderr}") from e

    def upload(self, local_path: str, remote_path: str) -> None:
        remote_file = f"{self.user}@{self.host}:{self.remote_path}/{remote_path}"

        try:
            subprocess.run(
                [
                    "scp",
                    "-i",
                    str(self.key_path),
                    "-P",
                    str(self.port),
                    "-o",
                    "StrictHostKeyChecking=no",
                    local_path,
                    remote_file,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"SCP upload failed: {e.stderr}") from e


class EncryptionHandler:
    def __init__(self, key: str):
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=32,
            salt=b"ofx-project-encryption-salt",
            iterations=100000,
            backend=default_backend(),
        )
        self.key = kdf.derive(key.encode())

    def encrypt_file(self, file_path: str) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        with open(file_path, "rb") as f:
            data = f.read()

        nonce = os.urandom(12)
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, data, None)

        return nonce + ciphertext

    def decrypt_file(self, encrypted_data: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        aesgcm = AESGCM(self.key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext

    def encrypt_data(self, data: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def setup_git_filters(self, repo_path: Path, patterns: list | None = None) -> None:
        import git

        if patterns is None:
            patterns = ["*"]

        ofx_cmd = "ofx"

        gitattributes = repo_path / ".gitattributes"
        with open(gitattributes, "w") as f:
            f.write("\n".join(f"{p} filter=ofx-crypt diff=ofx-crypt" for p in patterns))
            f.write("\n[attr]binary -diff -merge -text\n")

        repo = git.Repo(repo_path)
        config = repo.config_writer()

        config.set_value(
            "filter.ofx-crypt", "clean", f"{ofx_cmd} project encrypt-filter"
        )
        config.set_value(
            "filter.ofx-crypt", "smudge", f"{ofx_cmd} project decrypt-filter"
        )
        config.set_value("filter.ofx-crypt", "required", "true")

        config.set_value(
            "diff.ofx-crypt", "textconv", f"{ofx_cmd} project decrypt-filter"
        )

        config.release()


class GitHandler:
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
                    raise RuntimeError(
                        "No git remote configured. Add a remote URL in config."
                    )

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
                logger = logging.getLogger("ofx")
                logger.info("No local changes to push")

        except Exception as e:
            raise RuntimeError(f"Git sync failed: {e}") from e
