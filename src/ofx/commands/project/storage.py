import getpass
import json
import logging
import os
import subprocess
import tempfile
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

    def setup_git_filters(
        self, repo_path: Path, patterns: list | None = None
    ) -> None:
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


class S3Handler:
    def __init__(
        self,
        bucket: str,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        prefix: str = "",
    ):
        import boto3
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

    def sync(self, local_path: Path) -> None:
        import git
        logger = logging.getLogger("ofx")

        try:
            repo = git.Repo(local_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            raise RuntimeError(f"No git repository found at {local_path}") from None

        bundle_key = f"{self.prefix}/repo.bundle" if self.prefix else "repo.bundle"
        refs_key = f"{self.prefix}/refs.json" if self.prefix else "refs.json"

        with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bundle_file:
            bundle_path = bundle_file.name

        try:
            repo.git.bundle("create", bundle_path, "--all")
            logger.info(f"Created git bundle: {bundle_path}")

            self.s3.upload_file(bundle_path, self.bucket, bundle_key)
            logger.info(f"Uploaded bundle to s3://{self.bucket}/{bundle_key}")

            refs_data = {
                "refs": {ref.name: ref.commit.hexsha for ref in repo.refs},
                "head": repo.head.commit.hexsha if repo.head.is_valid() else None,
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as refs_file:
                json.dump(refs_data, refs_file)
                refs_path = refs_file.name

            self.s3.upload_file(refs_path, self.bucket, refs_key)
            logger.info(f"Uploaded refs to s3://{self.bucket}/{refs_key}")

            os.unlink(bundle_path)
            os.unlink(refs_path)

        except Exception as e:
            if os.path.exists(bundle_path):
                os.unlink(bundle_path)
            raise RuntimeError(f"Failed to sync to S3: {e}") from e

    def fetch(self, local_path: Path) -> None:
        import git
        logger = logging.getLogger("ofx")

        bundle_key = f"{self.prefix}/repo.bundle" if self.prefix else "repo.bundle"

        try:
            repo = git.Repo(local_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            repo = git.Repo.init(local_path)

        with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bundle_file:
            bundle_path = bundle_file.name

        try:
            self.s3.download_file(self.bucket, bundle_key, bundle_path)
            logger.info(f"Downloaded bundle from s3://{self.bucket}/{bundle_key}")

            repo.git.fetch(bundle_path)
            logger.info("Fetched changes from bundle")

            try:
                if "main" in [ref.name for ref in repo.refs]:
                    repo.git.checkout("main")
                    logger.info("Checked out main branch")
                elif "master" in [ref.name for ref in repo.refs]:
                    repo.git.checkout("master")
                    logger.info("Checked out master branch")
            except Exception as e:
                logger.debug(f"Could not checkout branch: {e}")

            os.unlink(bundle_path)

        except Exception as e:
            if os.path.exists(bundle_path):
                os.unlink(bundle_path)
            raise RuntimeError(f"Failed to fetch from S3: {e}") from e

    def upload(self, local_path: str, remote_path: str) -> None:
        key = f"{self.prefix}/{remote_path}" if self.prefix else remote_path
        self.s3.upload_file(local_path, self.bucket, key)

    def download(self, remote_path: str, local_path: str) -> None:
        key = f"{self.prefix}/{remote_path}" if self.prefix else remote_path
        self.s3.download_file(self.bucket, key, local_path)


class WebDAVHandler:
    def __init__(self, webdav_options: dict):
        from webdav3.client import Client as WebDAVClient
        self.client = WebDAVClient(webdav_options)
        self.base_path = webdav_options.get("webdav_root", "/")

    def sync(self, local_path: Path) -> None:
        import git
        logger = logging.getLogger("ofx")

        try:
            repo = git.Repo(local_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            raise RuntimeError(f"No git repository found at {local_path}") from None

        bundle_path_remote = f"{self.base_path}/repo.bundle".replace("//", "/")
        refs_path_remote = f"{self.base_path}/refs.json".replace("//", "/")

        with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bundle_file:
            bundle_path = bundle_file.name

        try:
            repo.git.bundle("create", bundle_path, "--all")
            logger.info(f"Created git bundle: {bundle_path}")

            self.client.upload_sync(
                remote_path=bundle_path_remote, local_path=bundle_path
            )
            logger.info(f"Uploaded bundle to WebDAV: {bundle_path_remote}")

            refs_data = {
                "refs": {ref.name: ref.commit.hexsha for ref in repo.refs},
                "head": repo.head.commit.hexsha if repo.head.is_valid() else None,
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as refs_file:
                json.dump(refs_data, refs_file)
                refs_path = refs_file.name

            self.client.upload_sync(remote_path=refs_path_remote, local_path=refs_path)
            logger.info(f"Uploaded refs to WebDAV: {refs_path_remote}")

            os.unlink(bundle_path)
            os.unlink(refs_path)

        except Exception as e:
            if os.path.exists(bundle_path):
                os.unlink(bundle_path)
            raise RuntimeError(f"Failed to sync to WebDAV: {e}") from e

    def fetch(self, local_path: Path) -> None:
        import git
        logger = logging.getLogger("ofx")

        bundle_path_remote = f"{self.base_path}/repo.bundle".replace("//", "/")

        try:
            repo = git.Repo(local_path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError):
            repo = git.Repo.init(local_path)

        with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bundle_file:
            bundle_path = bundle_file.name

        try:
            self.client.download_sync(
                remote_path=bundle_path_remote, local_path=bundle_path
            )
            logger.info(f"Downloaded bundle from WebDAV: {bundle_path_remote}")

            repo.git.fetch(bundle_path)
            logger.info("Fetched changes from bundle")

            try:
                if "main" in [ref.name for ref in repo.refs]:
                    repo.git.checkout("main")
                    logger.info("Checked out main branch")
                elif "master" in [ref.name for ref in repo.refs]:
                    repo.git.checkout("master")
                    logger.info("Checked out master branch")
            except Exception as e:
                logger.debug(f"Could not checkout branch: {e}")

            os.unlink(bundle_path)

        except Exception as e:
            if os.path.exists(bundle_path):
                os.unlink(bundle_path)
            raise RuntimeError(f"Failed to fetch from WebDAV: {e}") from e

    def upload(self, local_path: str, remote_path: str) -> None:
        self.client.upload_sync(remote_path=remote_path, local_path=local_path)

    def download(self, remote_path: str, local_path: str) -> None:
        self.client.download_sync(remote_path=remote_path, local_path=local_path)
