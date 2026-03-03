"""Encryption utilities for OFX project management.

Provides encryption key management and data encryption/decryption
using AES-256-GCM with PBKDF2 key derivation.

Wire format (v2)::

    [8 bytes magic "OFX_ENC\\x01"] [16 bytes salt] [12 bytes nonce] [ciphertext + GCM tag]

The magic header allows git filters and tooling to reliably distinguish
encrypted blobs from plaintext without heuristics.

Cross-platform: uses only the ``cryptography`` Python library — no
external ``openssl`` or shell commands required.
"""

import logging
import os
import secrets
from pathlib import Path

from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

ENCRYPTION_KEY_FILE = ".ofx-encryption-key"

# Magic bytes written at the start of every encrypted blob.
_MAGIC = b"OFX_ENC\x01"  # 8 bytes — version 1 of the wire format
_MAGIC_LEN = len(_MAGIC)
_SALT_LEN = 16
_NONCE_LEN = 12
_HEADER_LEN = _MAGIC_LEN + _SALT_LEN + _NONCE_LEN  # 36 bytes

# Legacy format used a static salt and no magic header.
_LEGACY_SALT = b"ofx-project-encryption-salt"
_KDF_ITERATIONS = 100_000


# ------------------------------------------------------------------
# Key management helpers
# ------------------------------------------------------------------


def generate_encryption_key() -> str:
    """Generate a new encryption key."""
    return secrets.token_urlsafe(32)


def find_encryption_key(project_path: Path) -> str | None:
    """Find encryption key by searching project and parent directories.

    Args:
        project_path: Project directory to start searching from.

    Returns:
        Encryption key string or ``None`` if not found.
    """
    check_dirs = [project_path, *project_path.parents]
    for parent in check_dirs:
        key_file = parent / ENCRYPTION_KEY_FILE
        if key_file.exists():
            return key_file.read_text().strip()
    return None


def save_encryption_key(project_path: Path, key: str) -> Path:
    """Save encryption key to project directory.

    Returns:
        Path to saved key file.
    """
    key_file = project_path / ENCRYPTION_KEY_FILE
    key_file.write_text(key)
    key_file.chmod(0o600)
    logger.info("Encryption key saved to %s", key_file)
    return key_file


def ensure_key_in_gitignore(project_path: Path) -> None:
    """Ensure encryption key file is in ``.gitignore``."""
    gitignore = project_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ENCRYPTION_KEY_FILE not in content:
            gitignore.write_text(content.rstrip() + f"\n{ENCRYPTION_KEY_FILE}\n")
    else:
        gitignore.write_text(f"{ENCRYPTION_KEY_FILE}\n")


def is_encrypted(data: bytes) -> bool:
    """Return ``True`` if *data* starts with the OFX encryption magic header."""
    return data[:_MAGIC_LEN] == _MAGIC


# ------------------------------------------------------------------
# Core encryption / decryption
# ------------------------------------------------------------------


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from *passphrase* and *salt* via PBKDF2."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode())


class EncryptionHandler:
    """Handles AES-256-GCM encryption/decryption for project files.

    Each ``encrypt_data`` call generates a fresh random salt and nonce,
    meaning identical plaintext produces different ciphertext every time.
    """

    def __init__(self, key: str):
        self._passphrase = key
        # Pre-derive a legacy key for backward-compatible decryption.
        self._legacy_key = _derive_key(key, _LEGACY_SALT)

    # -- public API ---------------------------------------------------

    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt *data* → ``magic + salt + nonce + ciphertext``.

        Returns:
            The encrypted blob including the 36-byte header.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        key = _derive_key(self._passphrase, salt)
        ciphertext = AESGCM(key).encrypt(nonce, data, _MAGIC)
        return _MAGIC + salt + nonce + ciphertext

    def decrypt_data(self, blob: bytes) -> bytes:
        """Decrypt a blob produced by ``encrypt_data``.

        Also handles legacy blobs (no magic header, static salt) for
        backward compatibility.

        Raises:
            ValueError: If decryption fails (wrong key or corrupt data).
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if is_encrypted(blob):
            # New v2 format
            salt = blob[_MAGIC_LEN : _MAGIC_LEN + _SALT_LEN]
            nonce = blob[_MAGIC_LEN + _SALT_LEN : _HEADER_LEN]
            ciphertext = blob[_HEADER_LEN:]
            key = _derive_key(self._passphrase, salt)
            try:
                return AESGCM(key).decrypt(nonce, ciphertext, _MAGIC)
            except Exception as exc:
                raise ValueError("Decryption failed — wrong key or corrupt data") from exc

        # Legacy format: first 12 bytes = nonce, rest = ciphertext, static salt
        if len(blob) < _NONCE_LEN + 1:
            raise ValueError("Data too short to be an encrypted blob")
        nonce = blob[:_NONCE_LEN]
        ciphertext = blob[_NONCE_LEN:]
        try:
            return AESGCM(self._legacy_key).decrypt(nonce, ciphertext, None)
        except Exception as exc:
            raise ValueError("Decryption failed — wrong key or corrupt data") from exc

    def encrypt_file(self, file_path: str) -> bytes:
        """Read and encrypt a file, returning the encrypted blob."""
        with open(file_path, "rb") as fh:
            return self.encrypt_data(fh.read())

    def decrypt_file(self, encrypted_data: bytes) -> bytes:
        """Decrypt a blob and return plaintext. Alias for ``decrypt_data``."""
        return self.decrypt_data(encrypted_data)

    # -- git filter setup ---------------------------------------------

    def setup_git_filters(self, repo_path: Path, patterns: list | None = None) -> None:
        """Set up git clean/smudge filters for transparent encryption."""
        import git

        if patterns is None:
            patterns = ["*"]

        ofx_cmd = "ofx"

        gitattributes = repo_path / ".gitattributes"
        with open(gitattributes, "w") as fh:
            fh.write(
                "\n".join(
                    f"{p} filter=ofx-crypt diff=ofx-crypt" for p in patterns
                )
            )
            fh.write("\n[attr]binary -diff -merge -text\n")

        repo = git.Repo(repo_path)
        config = repo.config_writer()

        config.set_value("filter.ofx-crypt", "clean", f"{ofx_cmd} project encrypt-filter")
        config.set_value("filter.ofx-crypt", "smudge", f"{ofx_cmd} project decrypt-filter")
        config.set_value("filter.ofx-crypt", "required", "true")
        config.set_value("diff.ofx-crypt", "textconv", f"{ofx_cmd} project decrypt-filter")

        config.release()


# ------------------------------------------------------------------
# Git filter handlers (called via hidden CLI commands)
# ------------------------------------------------------------------


class GitFilterHandler:
    """Git clean/smudge filter operations invoked by ``ofx project encrypt-filter``
    and ``ofx project decrypt-filter``.

    Works on all platforms — reads from stdin, writes to stdout using only
    Python standard I/O.
    """

    @staticmethod
    def encrypt_stdin_to_stdout() -> None:
        """Git *clean* filter: encrypt stdin → stdout."""
        import sys

        try:
            encryption_key = find_encryption_key(Path.cwd())
            if not encryption_key:
                # No key → pass-through (no encryption configured)
                sys.stdout.buffer.write(sys.stdin.buffer.read())
                return

            data = sys.stdin.buffer.read()
            handler = EncryptionHandler(encryption_key)
            sys.stdout.buffer.write(handler.encrypt_data(data))
        except Exception:
            # Safety: never corrupt the repository — pass data through on error
            import traceback

            logger.debug("encrypt-filter error: %s", traceback.format_exc())
            sys.stdout.buffer.write(sys.stdin.buffer.read())

    @staticmethod
    def decrypt_stdin_to_stdout() -> None:
        """Git *smudge* filter: decrypt stdin → stdout."""
        import sys

        try:
            encryption_key = find_encryption_key(Path.cwd())
            if not encryption_key:
                sys.stdout.buffer.write(sys.stdin.buffer.read())
                return

            data = sys.stdin.buffer.read()

            # If data doesn't look encrypted at all, pass through unchanged.
            if not is_encrypted(data) and len(data) < _NONCE_LEN + 1:
                sys.stdout.buffer.write(data)
                return

            handler = EncryptionHandler(encryption_key)
            sys.stdout.buffer.write(handler.decrypt_data(data))
        except Exception:
            # Safety: pass through on any error so the working tree stays usable
            import traceback

            logger.debug("decrypt-filter error: %s", traceback.format_exc())
            sys.stdout.buffer.write(sys.stdin.buffer.read())
