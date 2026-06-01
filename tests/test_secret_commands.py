from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from ofx.commands.secret import app


runner = CliRunner()


def test_secret_set_rejects_value_and_file_together(tmp_path, monkeypatch):
    file_path = tmp_path / "secret.txt"
    file_path.write_text("from-file")
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "ofx.commands.secret.manage.typer.secho",
        lambda message, **kwargs: calls.append((message, kwargs.get("fg"))),
    )

    result = runner.invoke(
        app,
        ["set", "API_KEY", "--value", "inline", "--file", str(file_path)],
    )

    assert result.exit_code == 1
    assert calls[0][0] == "❌ Use either --value or --file, not both"


def test_secret_set_rejects_missing_file(monkeypatch, tmp_path):
    missing = tmp_path / "missing.txt"
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "ofx.commands.secret.manage.typer.secho",
        lambda message, **kwargs: calls.append((message, kwargs.get("fg"))),
    )

    result = runner.invoke(app, ["set", "API_KEY", "--file", str(missing)])

    assert result.exit_code == 1
    assert calls[0][0] == f"❌ File not found: {missing}"


def test_secret_set_reads_value_from_file_and_parses_json(monkeypatch, tmp_path):
    file_path = tmp_path / "secret.json"
    file_path.write_text('{"token": "abc"}')
    saved: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "ofx.commands.secret.manage.secrets_store.secret_exists",
        lambda _name: False,
    )
    monkeypatch.setattr(
        "ofx.commands.secret.manage.secrets_store.set_secret",
        lambda name, value: saved.append((name, value)),
    )
    monkeypatch.setattr(
        "ofx.commands.secret.manage.print_success",
        lambda *args, **kwargs: None,
    )

    result = runner.invoke(app, ["set", "API_KEY", "--file", str(file_path)])

    assert result.exit_code == 0
    assert saved == [("API_KEY", {"token": "abc"})]


def test_secret_backup_create_uses_prompted_passphrase_over_flag(monkeypatch, tmp_path):
    output_file = tmp_path / "backup.enc"
    seen: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "ofx.commands.secret.backup.typer.prompt",
        lambda *args, **kwargs: " prompted-passphrase ",
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.secrets_store.list_secrets",
        lambda *, passphrase=None: seen.append(("list", passphrase))
        or {"API_KEY": "value"},
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.secrets_store.backup_secrets",
        lambda path, *, passphrase=None: seen.append(("backup", passphrase))
        or path.write_text("encrypted")
        or 1,
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.print_success",
        lambda *args, **kwargs: None,
    )

    result = runner.invoke(
        app,
        [
            "backup",
            "create",
            "--output",
            str(output_file),
            "--passphrase",
            "flag-passphrase",
            "--ask-passphrase",
        ],
    )

    assert result.exit_code == 0
    assert seen == [
        ("list", "prompted-passphrase"),
        ("backup", "prompted-passphrase"),
    ]


def test_secret_backup_restore_uses_none_for_blank_prompt(monkeypatch, tmp_path):
    backup_file = tmp_path / "backup.enc"
    backup_file.write_text("encrypted")
    seen: list[tuple[str, object]] = []

    monkeypatch.setattr(
        "ofx.commands.secret.backup.typer.prompt",
        lambda *args, **kwargs: "   ",
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.secrets_store.get_backup_info",
        lambda path, *, passphrase=None: seen.append(("info", passphrase))
        or {
            "created": "2024-01-01T00:00:00",
            "count": 1,
            "size": 12,
            "secrets": {"API_KEY": "value"},
        },
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.secrets_store.list_secrets",
        lambda *, passphrase=None: seen.append(("list", passphrase)) or {},
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.secrets_store.restore_secrets",
        lambda path, overwrite, *, passphrase=None: seen.append(
            ("restore", passphrase)
        )
        or 1,
    )
    monkeypatch.setattr(
        "ofx.commands.secret.backup.print_success",
        lambda *args, **kwargs: None,
    )

    result = runner.invoke(
        app,
        ["backup", "restore", str(backup_file), "--ask-passphrase"],
    )

    assert result.exit_code == 0
    assert seen == [
        ("info", None),
        ("list", None),
        ("restore", None),
    ]


def test_secret_list_show_values_warns_after_display(monkeypatch):
    console = Console(record=True, width=120)
    calls: list[tuple[str, object, object]] = []

    monkeypatch.setattr(
        "ofx.commands.secret.manage.secrets_store.list_secrets",
        lambda: {"API_KEY": "super-secret-token-value"},
    )
    monkeypatch.setattr("ofx.commands.secret.manage.get_console", lambda: console)
    monkeypatch.setattr(
        "ofx.commands.secret.manage.typer.secho",
        lambda message, **kwargs: calls.append(
            (message, kwargs.get("fg"), kwargs.get("bold"))
        ),
    )

    result = runner.invoke(app, ["list", "--show-values"])

    assert result.exit_code == 0
    assert "API_KEY" in console.export_text()
    assert calls == [
        (
            "\n⚠️ WARNING: Secret values are displayed above!",
            "yellow",
            True,
        )
    ]


def test_secret_list_renders_filtered_results(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr(
        "ofx.commands.secret.manage.secrets_store.list_secrets",
        lambda: {
            "API_KEY": "averylongtoken/with=chars+for-detection-1234567890-extra-padding",
            "PASSWORD": "Secret123",
        },
    )
    monkeypatch.setattr("ofx.commands.secret.manage.get_console", lambda: console)

    result = runner.invoke(app, ["list", "--filter", "token", "--show-values"])

    assert result.exit_code == 0
    output = console.export_text()
    assert "API_KEY" in output
    assert "PASSWORD" not in output
    assert "token" in output


def test_secret_search_renders_matches(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr(
        "ofx.commands.secret.manage.secrets_store.list_secrets",
        lambda: {
            "API_KEY": "value",
            "DB_PASSWORD": "Secret123",
        },
    )
    monkeypatch.setattr("ofx.commands.secret.manage.get_console", lambda: console)

    result = runner.invoke(app, ["search", "*password*"])

    assert result.exit_code == 0
    output = console.export_text()
    assert "DB_PASSWORD" in output
    assert "API_KEY" not in output
    assert "Search Results" in output
