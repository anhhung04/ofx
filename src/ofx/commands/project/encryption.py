"""Encryption utilities for OFX project management.

Provides encryption key management and data encryption/decryption
using AES-GCM with PBKDF2 key derivation.
"""

import logging
import os
import secrets
from pathlib import Path

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

ENCRYPTION_KEY_FILE = ".ofx-encryption-key"
ENCRYPTION_SALT = b"ofx-project-encryption-salt"


def generate_encryption_key() -> str:
    """Generate a new encryption key."""
    return secrets.token_urlsafe(32)


def find_encryption_key(project_path: Path) -> str | None:
    """Find encryption key by searching project and parent directories.
    
    Args:
        project_path: Project directory to start searching from
        
    Returns:
        Encryption key string or None if not found
    """
    check_dirs = [project_path]
    check_dirs.extend(project_path.parents)
    
    for parent in check_dirs:
        key_file = parent / ENCRYPTION_KEY_FILE
        if key_file.exists():
            return key_file.read_text().strip()
    
    return None


def save_encryption_key(project_path: Path, key: str) -> Path:
    """Save encryption key to project directory.
    
    Args:
        project_path: Project directory
        key: Encryption key to save
        
    Returns:
        Path to saved key file
    """
    key_file = project_path / ENCRYPTION_KEY_FILE
    key_file.write_text(key)
    key_file.chmod(0o600)
    logger.info(f"Encryption key saved to {key_file}")
    return key_file


def ensure_key_in_gitignore(project_path: Path) -> None:
    """Ensure encryption key file is in .gitignore."""
    gitignore = project_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ENCRYPTION_KEY_FILE not in content:
            gitignore.write_text(content.rstrip() + f"\n{ENCRYPTION_KEY_FILE}\n")
    else:
        gitignore.write_text(f"{ENCRYPTION_KEY_FILE}\n")


class EncryptionHandler:
    """Handles AES-GCM encryption/decryption for project files."""
    
    def __init__(self, key: str):
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=32,
            salt=ENCRYPTION_SALT,
            iterations=100000,
            backend=default_backend(),
        )
        self.key = kdf.derive(key.encode())

    def encrypt_file(self, file_path: str) -> bytes:
        """Encrypt a file and return ciphertext with nonce prepended."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        with open(file_path, "rb") as f:
            data = f.read()

        return self.encrypt_data(data)

    def decrypt_file(self, encrypted_data: bytes) -> bytes:
        """Decrypt data (nonce + ciphertext) and return plaintext."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        aesgcm = AESGCM(self.key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt data and return nonce + ciphertext."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def setup_git_filters(self, repo_path: Path, patterns: list | None = None) -> None:
        """Setup git clean/smudge filters for transparent encryption."""
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

        config.set_value("filter.ofx-crypt", "clean", f"{ofx_cmd} project encrypt-filter")
        config.set_value("filter.ofx-crypt", "smudge", f"{ofx_cmd} project decrypt-filter")
        config.set_value("filter.ofx-crypt", "required", "true")
        config.set_value("diff.ofx-crypt", "textconv", f"{ofx_cmd} project decrypt-filter")

        config.release()


class GitFilterHandler:
    """Handles git filter operations for encryption."""
    
    @staticmethod
    def encrypt_stdin_to_stdout() -> None:
        """Git clean filter: Encrypt stdin to stdout."""
        import sys
        
        try:
            encryption_key = find_encryption_key(Path.cwd())
            if not encryption_key:
                sys.stdout.buffer.write(sys.stdin.buffer.read())
                return

            data = sys.stdin.buffer.read()
            encryptor = EncryptionHandler(encryption_key)
            encrypted = encryptor.encrypt_data(data)
            sys.stdout.buffer.write(encrypted)
        except Exception:
            sys.stdout.buffer.write(sys.stdin.buffer.read())

    @staticmethod
    def decrypt_stdin_to_stdout() -> None:
        """Git smudge filter: Decrypt stdin to stdout."""
        import sys
        
        try:
            encryption_key = find_encryption_key(Path.cwd())
            if not encryption_key:
                sys.stdout.buffer.write(sys.stdin.buffer.read())
                return

            data = sys.stdin.buffer.read()
            
            # Need at least nonce (12 bytes) + some ciphertext
            if len(data) < 13:
                sys.stdout.buffer.write(data)
                return

            encryptor = EncryptionHandler(encryption_key)
            decrypted = encryptor.decrypt_file(data)
            sys.stdout.buffer.write(decrypted)
        except Exception:
            sys.stdout.buffer.write(sys.stdin.buffer.read())
