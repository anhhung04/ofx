"""Encrypt and decrypt session results with a user-provided passphrase.

Uses Fernet symmetric encryption (AES-128-CBC) with PBKDF2-derived keys,
matching the pattern established by the OFX SecretStore.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import tarfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("ofx")

_SALT_PREFIX = os.getenv("USER", "ofx").encode()[:4].ljust(4, b"_") + os.getenv("HOSTNAME", "ofx-session")[:12].encode().ljust(12, b"_")
_KDF_ITERATIONS = 100_000


def derive_key(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a Fernet key from a passphrase.

    Args:
        passphrase: User-provided passphrase.
        salt: Optional salt bytes. If None, generates 16 random bytes.

    Returns:
        (fernet_key, salt) — both needed for decryption.
    """
    if salt is None:
        salt = os.urandom(16)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT_PREFIX + salt,
        iterations=_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
    return key, salt


def encrypt_results(results_dir: Path, passphrase: str, output_file: Path | None = None) -> Path:
    """Tar + encrypt a results directory.

    Args:
        results_dir: Directory containing result files to encrypt.
        passphrase: Encryption passphrase.
        output_file: Destination path. Defaults to ``results_dir.parent / "results.enc"``.

    Returns:
        Path to the encrypted file.

    Raises:
        FileNotFoundError: If results_dir doesn't exist or is empty.
    """
    if not results_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    files = list(results_dir.rglob("*"))
    if not any(f.is_file() for f in files):
        raise FileNotFoundError(f"No files found in {results_dir}")

    if output_file is None:
        output_file = results_dir.parent / "results.enc"

    # Create tar.gz in memory
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(results_dir), arcname="results")
    tar_data = buf.getvalue()

    # Encrypt
    key, salt = derive_key(passphrase)
    cipher = Fernet(key)
    encrypted = cipher.encrypt(tar_data)

    # Write: [16 bytes salt][encrypted data]
    output_file.write_bytes(salt + encrypted)
    output_file.chmod(0o600)

    logger.debug(
        "Encrypted %d files (%d bytes) → %s",
        sum(1 for f in files if f.is_file()),
        len(tar_data),
        output_file,
    )
    return output_file


def decrypt_results(
    enc_file: Path, passphrase: str, output_dir: Path | None = None
) -> Path:
    """Decrypt an encrypted results archive.

    Args:
        enc_file: Path to the ``.enc`` file.
        passphrase: Passphrase used during encryption.
        output_dir: Where to extract. Defaults to ``enc_file.parent / "results"``.

    Returns:
        Path to the extracted directory.

    Raises:
        FileNotFoundError: If enc_file doesn't exist.
        ValueError: If the passphrase is wrong or data is corrupt.
    """
    if not enc_file.exists():
        raise FileNotFoundError(f"Encrypted file not found: {enc_file}")

    raw = enc_file.read_bytes()
    if len(raw) < 16:
        raise ValueError("Encrypted file is too small — corrupt or not an OFX archive")

    salt = raw[:16]
    encrypted = raw[16:]

    key, _ = derive_key(passphrase, salt=salt)
    cipher = Fernet(key)

    try:
        tar_data = cipher.decrypt(encrypted)
    except InvalidToken:
        raise ValueError("Decryption failed — wrong passphrase or corrupt file") from None

    if output_dir is None:
        output_dir = enc_file.parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    buf = io.BytesIO(tar_data)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(path=str(output_dir), filter="data")

    logger.debug("Decrypted → %s", output_dir)
    return output_dir
