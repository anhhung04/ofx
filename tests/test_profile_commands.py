import importlib

from types import SimpleNamespace

from rich.console import Console
from typer.testing import CliRunner

from ofx.commands.flow.profile_commands import app


runner = CliRunner()
profile_commands = importlib.import_module("ofx.commands.flow.profile_commands")


def test_add_profile_uses_module_manager_and_parses_nested_values(monkeypatch):
    console = Console(record=True, width=120)
    calls: list[tuple[str, dict]] = []
    defaults: list[str] = []

    class FakeManager:
        def add(self, name, data):
            calls.append((name, data))

        def set_default(self, name):
            defaults.append(name)

    def broken_manager():
        raise RuntimeError("should not use ofx.profiles.manager.get_profile_manager")

    monkeypatch.setattr(profile_commands, "get_profile_manager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)
    monkeypatch.setattr("ofx.profiles.manager.get_profile_manager", broken_manager)
    monkeypatch.setattr("ofx.settings.get_console", lambda: None)

    result = runner.invoke(
        app,
        [
            "add",
            "stealth",
            "--desc",
            "Quiet profile",
            "--set",
            "time_window.enabled=true",
            "--set",
            "threads=5",
            "--set",
            "targets=[a,b]",
            "--default",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "stealth",
            {
                "description": "Quiet profile",
                "time_window": {"enabled": True},
                "threads": 5,
                "targets": ["a", "b"],
            },
        )
    ]
    assert defaults == ["stealth"]
    assert "Profile 'stealth' saved" in console.export_text()


def test_add_profile_rejects_invalid_set_syntax(monkeypatch):
    console = Console(record=True, width=120)

    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)

    result = runner.invoke(app, ["add", "broken", "--set", "noequals"])

    assert result.exit_code == 1
    assert "Invalid format 'noequals'" in console.export_text()


def test_add_profile_parses_false_and_float_values(monkeypatch):
    console = Console(record=True, width=120)
    calls: list[tuple[str, dict]] = []

    class FakeManager:
        def add(self, name, data):
            calls.append((name, data))

        def set_default(self, name):
            raise AssertionError("should not set default")

    monkeypatch.setattr(profile_commands, "get_profile_manager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)

    result = runner.invoke(
        app,
        [
            "add",
            "balanced",
            "--set",
            "time_window.enabled=false",
            "--set",
            "ratio=1.5",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "balanced",
            {
                "time_window": {"enabled": False},
                "ratio": 1.5,
            },
        )
    ]


def test_remove_profile_uses_module_manager(monkeypatch):
    console = Console(record=True, width=120)
    removed: list[str] = []

    class FakeManager:
        def remove(self, name):
            removed.append(name)

    monkeypatch.setattr(profile_commands, "get_profile_manager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)

    result = runner.invoke(app, ["remove", "stealth"])

    assert result.exit_code == 0
    assert removed == ["stealth"]
    assert "Profile 'stealth' removed" in console.export_text()


def test_set_default_uses_module_manager(monkeypatch):
    console = Console(record=True, width=120)
    defaults: list[str] = []

    class FakeManager:
        def set_default(self, name):
            defaults.append(name)

    monkeypatch.setattr(profile_commands, "get_profile_manager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)

    result = runner.invoke(app, ["default", "stealth"])

    assert result.exit_code == 0
    assert defaults == ["stealth"]
    assert "Default profile set to 'stealth'" in console.export_text()


def test_list_profiles_empty_shows_hint(monkeypatch):
    console = Console(record=True, width=120)

    class FakeManager:
        default_profile_name = ""

        def list_profiles(self):
            return []

    monkeypatch.setattr(profile_commands, "get_profile_manager", lambda: FakeManager(), raising=False)
    monkeypatch.setattr(profile_commands, "get_console", lambda: console, raising=False)

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    output = console.export_text()
    assert "No profiles configured" in output
    assert "ofx flow profile add <name> --set rate_limit=30" in output
