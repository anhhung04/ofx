"""Tests for the refactored encryption module (v2 wire format)."""

import os
import tempfile

import pytest


def test_v2_round_trip():
    """v2 format: magic + salt + nonce + ciphertext round-trips correctly."""
    from ofx.commands.project.encryption import (
        EncryptionHandler,
        _HEADER_LEN,
        _MAGIC,
        generate_encryption_key,
        is_encrypted,
    )

    key = generate_encryption_key()
    handler = EncryptionHandler(key)
    plaintext = b"Hello, OFX encryption v2!"
    blob = handler.encrypt_data(plaintext)

    assert blob[:8] == _MAGIC
    assert is_encrypted(blob)
    # 36 header + plaintext + 16 GCM tag
    assert len(blob) == _HEADER_LEN + len(plaintext) + 16

    assert handler.decrypt_data(blob) == plaintext


def test_encrypt_file_decrypt_file():
    """encrypt_file / decrypt_file aliases work correctly."""
    from ofx.commands.project.encryption import (
        EncryptionHandler,
        generate_encryption_key,
        is_encrypted,
    )

    key = generate_encryption_key()
    handler = EncryptionHandler(key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"file content test")
        f.flush()
        encrypted = handler.encrypt_file(f.name)
        os.unlink(f.name)

    assert is_encrypted(encrypted)
    assert handler.decrypt_file(encrypted) == b"file content test"


def test_legacy_backward_compat():
    """Legacy format (no magic, static salt) can still be decrypted."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    from ofx.commands.project.encryption import (
        EncryptionHandler,
        generate_encryption_key,
    )

    key = generate_encryption_key()
    handler = EncryptionHandler(key)

    # Produce legacy blob manually
    legacy_salt = b"ofx-project-encryption-salt"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA512(), length=32, salt=legacy_salt, iterations=100_000
    )
    legacy_key = kdf.derive(key.encode())
    nonce = os.urandom(12)
    legacy_blob = nonce + AESGCM(legacy_key).encrypt(nonce, b"legacy data", None)

    assert handler.decrypt_data(legacy_blob) == b"legacy data"


def test_is_encrypted_negative():
    """is_encrypted rejects non-encrypted data."""
    from ofx.commands.project.encryption import is_encrypted

    assert not is_encrypted(b"plain text")
    assert not is_encrypted(b"")
    assert not is_encrypted(b"\x00" * 7)


def test_different_ciphertext_each_time():
    """Encrypting the same data twice produces different blobs (random salt+nonce)."""
    from ofx.commands.project.encryption import EncryptionHandler, generate_encryption_key

    key = generate_encryption_key()
    handler = EncryptionHandler(key)
    blob1 = handler.encrypt_data(b"same")
    blob2 = handler.encrypt_data(b"same")
    assert blob1 != blob2


def test_wrong_key_raises():
    """Decryption with wrong key raises ValueError."""
    from ofx.commands.project.encryption import EncryptionHandler, generate_encryption_key

    key1 = generate_encryption_key()
    key2 = generate_encryption_key()
    blob = EncryptionHandler(key1).encrypt_data(b"secret")

    with pytest.raises(ValueError, match="Decryption failed"):
        EncryptionHandler(key2).decrypt_data(blob)


def test_storage_imports():
    """SSHHandler and GitHandler can be imported without paramiko."""
    from ofx.commands.project.storage import GitHandler, SSHHandler, _generate_ssh_keypair

    assert SSHHandler is not None
    assert GitHandler is not None
    assert callable(_generate_ssh_keypair)


def test_ssh_keygen_pure_python():
    """SSH key generation via cryptography library produces valid keys."""
    from ofx.commands.project.storage import _generate_ssh_keypair

    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "test_key")
        from pathlib import Path

        pub_key = _generate_ssh_keypair(Path(key_path))

        # Private key file created and is PEM
        assert os.path.exists(key_path)
        with open(key_path, "rb") as f:
            content = f.read()
        assert content.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----")

        # Public key in OpenSSH format
        assert pub_key.startswith("ssh-rsa ")
        assert "ofx-project-sync" in pub_key

        # .pub file exists
        assert os.path.exists(key_path + ".pub")
