from pathlib import Path

from ofx.utils.secrets import (
    backup_secrets,
    clear_secrets,
    delete_secret,
    get_backup_info,
    get_secret,
    get_store_info,
    list_secrets,
    load_secrets,
    load_secrets_by_keys,
    restore_secrets,
    secret_exists,
    set_secret,
)


def test_secret_crud_roundtrip(tmp_path: Path):
    store_path = tmp_path / "secrets.store"

    set_secret("API_KEY", "secret", store_path=store_path, passphrase="")

    assert get_secret("API_KEY", store_path=store_path, passphrase="") == "secret"
    assert list_secrets(store_path=store_path, passphrase="") == {"API_KEY": "secret"}
    assert secret_exists("API_KEY", store_path=store_path, passphrase="") is True
    assert delete_secret("API_KEY", store_path=store_path, passphrase="") is True
    assert secret_exists("API_KEY", store_path=store_path, passphrase="") is False

    clear_secrets(store_path=store_path, passphrase="")
    assert list_secrets(store_path=store_path, passphrase="") == {}


def test_load_secrets_by_keys_falls_back_to_directory(tmp_path: Path):
    store_path = tmp_path / "secrets.store"
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "DIR_ONLY").write_text("dir-secret")

    set_secret("STORE_ONLY", "store-secret", store_path=store_path, passphrase="")

    result = load_secrets_by_keys(
        {"STORE_ONLY", "DIR_ONLY"},
        secrets_dir=secrets_dir,
        passphrase="",
    )

    assert result == {
        "STORE_ONLY": "store-secret",
        "DIR_ONLY": "dir-secret",
    }


def test_load_secrets_falls_back_to_directory_when_store_empty(tmp_path: Path):
    import ofx.utils.secrets as secrets_module

    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    (secrets_dir / "DIR_ONLY").write_text("dir-secret")

    with __import__("pytest").MonkeyPatch.context() as mp:
        mp.setattr(secrets_module, "list_secrets", lambda *args, **kwargs: {})
        assert load_secrets(secrets_dir=secrets_dir) == {"DIR_ONLY": "dir-secret"}


def test_backup_restore_and_info_roundtrip(tmp_path: Path):
    store_path = tmp_path / "secrets.store"
    backup_path = tmp_path / "backup.bin"

    set_secret("API_KEY", "secret", store_path=store_path, passphrase="")
    set_secret("TOKEN", "token", store_path=store_path, passphrase="")

    assert backup_secrets(backup_path, store_path=store_path, passphrase="") == 2

    clear_secrets(store_path=store_path, passphrase="")
    assert restore_secrets(backup_path, store_path=store_path, passphrase="") == 2
    assert list_secrets(store_path=store_path, passphrase="") == {
        "API_KEY": "secret",
        "TOKEN": "token",
    }

    info = get_backup_info(backup_path, store_path=store_path, passphrase="")
    assert info["count"] == 2
    assert info["version"] == "1.0"
    assert info["secrets"] == {"API_KEY": "secret", "TOKEN": "token"}


def test_get_store_info_uses_explicit_store_path(tmp_path: Path):
    store_path = tmp_path / "custom.store"

    set_secret("API_KEY", "secret", store_path=store_path, passphrase="")

    info = get_store_info(store_path=store_path, passphrase="")

    assert info["path"] == str(store_path)
    assert info["exists"] is True
    assert info["count"] == 1
