from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import typer
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("ofx")


class SecretStore:
    _instance: SecretStore | None = None
    _store_path: Path | None = None
    _passphrase: str | None = None

    def __new__(cls, store_path: Path | None = None, passphrase: str | None = None):
        needs_new_instance = (
            cls._instance is None
            or (store_path and store_path != cls._store_path)
            or (passphrase is not None and passphrase != cls._passphrase)
        )

        if needs_new_instance:
            cls._instance = super().__new__(cls)
            cls._store_path = store_path
            cls._passphrase = passphrase
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, store_path: Path | None = None, passphrase: str | None = None):
        if self._initialized:
            return

        if store_path:
            self.store_path = store_path
        elif self._store_path:
            self.store_path = self._store_path
        else:
            from ofx.settings import SECRETS_STORE

            self.store_path = SECRETS_STORE

        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._cipher = None
        self._initialized = True

        if self.is_store_encrypted(self.store_path) and passphrase is None:
            env_passphrase = os.getenv(
                "OFX_SECRETS_PASSPHRASE",
                typer.prompt(
                    "Enter passphrase for secrets store (leave blank for none): ",
                    hide_input=True,
                ).strip()
                or None,
            )
            self._passphrase = env_passphrase
        else:
            self._passphrase = passphrase

    @classmethod
    def is_store_encrypted(cls, store_path: Path) -> bool:
        # try decrypt with empty passphrase; if it fails, assume it's encrypted
        if not store_path.exists():
            return False
        try:
            temp_instance = cls(store_path=store_path, passphrase="")
            temp_instance._get_cipher().decrypt(store_path.read_bytes())
            return False
        except Exception:
            return True

    @classmethod
    def get_instance(
        cls, store_path: Path | None = None, passphrase: str | None = None
    ) -> SecretStore:
        return cls(store_path, passphrase)

    def _get_key(self) -> bytes:
        machine_id = self._get_machine_id()
        username = os.getenv("USER", os.getenv("USERNAME", "default"))
        salt = b"ofx-secret-store-v1"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        passphrase = self._passphrase or ""
        key_material = f"{machine_id}:{username}:{passphrase}".encode()
        key = base64.urlsafe_b64encode(kdf.derive(key_material))
        return key

    def _get_machine_id(self) -> str:
        machine_id_paths = [
            Path("/etc/machine-id"),
            Path("/var/lib/dbus/machine-id"),
        ]

        for path in machine_id_paths:
            if path.exists():
                return path.read_text().strip()

        import socket

        return socket.gethostname()

    def _get_cipher(self) -> Fernet:
        if self._cipher is None:
            self._cipher = Fernet(self._get_key())
        return self._cipher

    def _load_data(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {}

        try:
            encrypted_data = self.store_path.read_bytes()
            decrypted_data = self._get_cipher().decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.warning("Failed to decrypt secret store: %s", e)
            return {}

    def _save_data(self, data: dict[str, Any]) -> None:
        json_data = json.dumps(data, indent=2).encode()
        encrypted_data = self._get_cipher().encrypt(json_data)
        self.store_path.write_bytes(encrypted_data)
        self.store_path.chmod(0o600)

    def set(self, name: str, value: Any) -> None:
        data = self._load_data()
        data[name] = value
        self._save_data(data)

    def get(self, name: str) -> Any:
        data = self._load_data()
        return data.get(name)

    def delete(self, name: str) -> bool:
        data = self._load_data()
        if name in data:
            del data[name]
            self._save_data(data)
            return True
        return False

    def get_many(self, names: set[str]) -> dict[str, Any]:
        """Load only the specified secret keys from the store."""
        if not names:
            return {}
        data = self._load_data()
        return {k: v for k, v in data.items() if k in names}

    def list(self) -> dict[str, Any]:
        return self._load_data()

    def clear(self) -> None:
        if self.store_path.exists():
            self.store_path.unlink()

    def exists(self, name: str) -> bool:
        return name in self._load_data()

    def export_unencrypted(self) -> dict[str, Any]:
        return self._load_data()

    def import_unencrypted(self, data: dict[str, Any], overwrite: bool = False) -> None:
        existing = self._load_data()
        if overwrite:
            existing.update(data)
        else:
            for key, value in data.items():
                if key not in existing:
                    existing[key] = value
        self._save_data(existing)


def _with_store(
    store_path: Path | None = None, passphrase: str | None = None
) -> SecretStore:
    """Get a SecretStore instance (shorthand for the common pattern)."""
    return SecretStore.get_instance(store_path, passphrase)


def set_secret(name: str, value: Any, store_path: Path | None = None, passphrase: str | None = None) -> None:
    _with_store(store_path, passphrase).set(name, value)


def get_secret(name: str, store_path: Path | None = None, passphrase: str | None = None) -> Any:
    return _with_store(store_path, passphrase).get(name)


def delete_secret(name: str, store_path: Path | None = None, passphrase: str | None = None) -> bool:
    return _with_store(store_path, passphrase).delete(name)


def list_secrets(store_path: Path | None = None, passphrase: str | None = None) -> dict[str, Any]:
    return _with_store(store_path, passphrase).list()


def secret_exists(name: str, store_path: Path | None = None, passphrase: str | None = None) -> bool:
    return _with_store(store_path, passphrase).exists(name)


def clear_secrets(store_path: Path | None = None, passphrase: str | None = None) -> None:
    _with_store(store_path, passphrase).clear()


def export_secrets(output_path: Path, store_path: Path | None = None, passphrase: str | None = None) -> int:
    secrets = _with_store(store_path, passphrase).export_unencrypted()
    if secrets:
        output_path.write_text(json.dumps(secrets, indent=2))
    return len(secrets)


def import_secrets_from_file(
    input_path: Path, overwrite: bool = False,
    store_path: Path | None = None, passphrase: str | None = None,
) -> int:
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")
    try:
        data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    store = _with_store(store_path, passphrase)
    existing_count = len(store.list())
    store.import_unencrypted(data, overwrite)
    return len(data) if overwrite else len(store.list()) - existing_count


def migrate_from_directory(
    directory: Path, store_path: Path | None = None, passphrase: str | None = None
) -> int:
    if not directory.exists() or not list(directory.glob("*")):
        return 0
    secrets = {}
    for secret_file in directory.glob("*"):
        if secret_file.is_file():
            content = secret_file.read_text()
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass
            secrets[secret_file.name] = content
    _with_store(store_path, passphrase).import_unencrypted(secrets, overwrite=False)
    return len(secrets)


def get_store_path(store_path: Path | None = None) -> Path:
    if store_path:
        return store_path
    from ofx.settings import SECRETS_STORE
    return SECRETS_STORE


def get_store_info(store_path: Path | None = None, passphrase: str | None = None) -> dict[str, Any]:
    path = get_store_path(store_path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "count": len(list_secrets(store_path, passphrase)),
    }


def _load_backup_data(backup_path: Path, store: SecretStore) -> dict:
    """Decrypt and parse a backup file, returning the full backup dict."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")
    encrypted_data = backup_path.read_bytes()
    decrypted_data = store._get_cipher().decrypt(encrypted_data)
    backup_data = json.loads(decrypted_data.decode())
    if not isinstance(backup_data, dict):
        raise ValueError("Invalid backup file format")
    return backup_data


def backup_secrets(
    output_path: Path, store_path: Path | None = None, passphrase: str | None = None
) -> int:
    """Create an encrypted backup of all secrets with metadata."""
    store = _with_store(store_path, passphrase)
    secrets = store.export_unencrypted()
    if not secrets:
        return 0

    from datetime import datetime
    backup_data = {
        "metadata": {
            "version": "1.0", "created": datetime.now().isoformat(),
            "count": len(secrets), "type": "ofx-secret-backup",
        },
        "secrets": secrets,
    }
    json_data = json.dumps(backup_data, indent=2).encode()
    encrypted_data = store._get_cipher().encrypt(json_data)
    output_path.write_bytes(encrypted_data)
    output_path.chmod(0o600)
    return len(secrets)


def restore_secrets(
    backup_path: Path, overwrite: bool = False,
    store_path: Path | None = None, passphrase: str | None = None,
) -> int:
    """Restore secrets from an encrypted backup."""
    store = _with_store(store_path, passphrase)
    backup_data = _load_backup_data(backup_path, store)
    if "secrets" not in backup_data:
        raise ValueError("Invalid backup file format")

    existing = store.list()
    imported = 0
    for name, value in backup_data["secrets"].items():
        if name not in existing or overwrite:
            store.set(name, value)
            imported += 1
    return imported


def get_backup_info(
    backup_path: Path, store_path: Path | None = None, passphrase: str | None = None
) -> dict[str, Any]:
    """Get information about a backup file without restoring it."""
    store = _with_store(store_path, passphrase)
    backup_data = _load_backup_data(backup_path, store)
    if "metadata" not in backup_data:
        raise ValueError("Invalid backup file format")

    from datetime import datetime
    metadata = backup_data["metadata"]
    secrets = backup_data.get("secrets", {})
    return {
        "created": datetime.fromisoformat(metadata["created"]),
        "count": metadata.get("count", len(secrets)),
        "size": backup_path.stat().st_size,
        "version": metadata.get("version", "unknown"),
        "secrets": secrets,
    }


def _load_dir_secrets(secrets_dir: Path, keys: set[str] | None = None) -> dict[str, Any]:
    """Load secrets from a legacy directory, optionally filtered by keys."""
    result: dict[str, Any] = {}
    if not secrets_dir or not secrets_dir.exists():
        return result
    for secret_file in secrets_dir.glob("*"):
        if not secret_file.is_file():
            continue
        if keys and secret_file.name not in keys:
            continue
        content = secret_file.read_text()
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass
        result[secret_file.name] = content
    return result


def load_secrets(secrets_dir: Path | None = None) -> dict[str, str]:
    """Load secrets from encrypted store, falling back to directory."""
    secrets = list_secrets()
    if not secrets and secrets_dir:
        secrets = _load_dir_secrets(secrets_dir)
    return secrets


def load_secrets_by_keys(
    keys: set[str], secrets_dir: Path | None = None, passphrase: str | None = None,
) -> dict[str, str]:
    """Load only the specified secrets, falling back to directory for missing keys."""
    if not keys:
        return {}
    result = _with_store(passphrase=passphrase).get_many(keys)
    missing = keys - result.keys()
    if missing and secrets_dir:
        result.update(_load_dir_secrets(secrets_dir, missing))
    return result
