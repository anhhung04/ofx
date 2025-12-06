import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecretStore:
    _instance: Optional["SecretStore"] = None
    _store_path: Optional[Path] = None

    def __new__(cls, store_path: Optional[Path] = None):
        if cls._instance is None or (store_path and store_path != cls._store_path):
            cls._instance = super().__new__(cls)
            cls._store_path = store_path
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, store_path: Optional[Path] = None):
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

    @classmethod
    def get_instance(cls, store_path: Optional[Path] = None) -> "SecretStore":
        return cls(store_path)

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
        key_material = f"{machine_id}:{username}".encode()
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

    def _load_data(self) -> Dict[str, Any]:
        if not self.store_path.exists():
            return {}

        try:
            encrypted_data = self.store_path.read_bytes()
            decrypted_data = self._get_cipher().decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception:
            return {}

    def _save_data(self, data: Dict[str, Any]) -> None:
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

    def list(self) -> Dict[str, Any]:
        return self._load_data()

    def clear(self) -> None:
        if self.store_path.exists():
            self.store_path.unlink()

    def exists(self, name: str) -> bool:
        return name in self._load_data()

    def export_unencrypted(self) -> Dict[str, Any]:
        return self._load_data()

    def import_unencrypted(self, data: Dict[str, Any], overwrite: bool = False) -> None:
        existing = self._load_data()
        if overwrite:
            existing.update(data)
        else:
            for key, value in data.items():
                if key not in existing:
                    existing[key] = value
        self._save_data(existing)


class SecretManager:
    @staticmethod
    def set(name: str, value: Any, store_path: Optional[Path] = None) -> None:
        store = SecretStore.get_instance(store_path)
        store.set(name, value)

    @staticmethod
    def get(name: str, store_path: Optional[Path] = None) -> Any:
        store = SecretStore.get_instance(store_path)
        return store.get(name)

    @staticmethod
    def delete(name: str, store_path: Optional[Path] = None) -> bool:
        store = SecretStore.get_instance(store_path)
        return store.delete(name)

    @staticmethod
    def list(store_path: Optional[Path] = None) -> Dict[str, Any]:
        store = SecretStore.get_instance(store_path)
        return store.list()

    @staticmethod
    def exists(name: str, store_path: Optional[Path] = None) -> bool:
        store = SecretStore.get_instance(store_path)
        return store.exists(name)

    @staticmethod
    def clear(store_path: Optional[Path] = None) -> None:
        store = SecretStore.get_instance(store_path)
        store.clear()

    @staticmethod
    def export(output_path: Path, store_path: Optional[Path] = None) -> int:
        store = SecretStore.get_instance(store_path)
        secrets = store.export_unencrypted()
        if secrets:
            output_path.write_text(json.dumps(secrets, indent=2))
        return len(secrets)

    @staticmethod
    def import_from_file(
        input_path: Path, overwrite: bool = False, store_path: Optional[Path] = None
    ) -> int:
        if not input_path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        try:
            data = json.loads(input_path.read_text())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        store = SecretStore.get_instance(store_path)
        existing_count = len(store.list())
        store.import_unencrypted(data, overwrite)
        new_count = len(store.list())

        return new_count - existing_count if not overwrite else len(data)

    @staticmethod
    def migrate_from_directory(
        directory: Path, store_path: Optional[Path] = None
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

        store = SecretStore.get_instance(store_path)
        store.import_unencrypted(secrets, overwrite=False)
        return len(secrets)

    @staticmethod
    def get_store_path(store_path: Optional[Path] = None) -> Path:
        if store_path:
            return store_path
        from ofx.settings import SECRETS_STORE

        return SECRETS_STORE

    @staticmethod
    def get_store_info(store_path: Optional[Path] = None) -> Dict[str, Any]:
        path = SecretManager.get_store_path(store_path)
        info = {
            "path": str(path),
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "count": len(SecretManager.list(store_path)),
        }
        return info
