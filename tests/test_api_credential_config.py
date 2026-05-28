from __future__ import annotations

from configparser import ConfigParser

from ofx.api.credential_config import load_section_values, save_section_values


def test_load_section_values_returns_requested_keys(tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text("[Fofa]\nUser = user@example.com\nToken = secret\n")

    parser, values = load_section_values(config_path, "Fofa", ("User", "Token"))

    assert parser.has_section("Fofa")
    assert values == {"User": "user@example.com", "Token": "secret"}


def test_save_section_values_preserves_existing_sections(tmp_path):
    config_path = tmp_path / "config.ini"
    parser = ConfigParser()
    parser.add_section("Other")
    parser.set("Other", "value", "kept")

    save_section_values(config_path, parser, "Shodan", {"Token": "abc123"})

    loaded = ConfigParser()
    loaded.read(config_path)

    assert loaded.get("Other", "value") == "kept"
    assert loaded.get("Shodan", "Token") == "abc123"


def test_save_section_values_ignores_none_values(tmp_path):
    config_path = tmp_path / "config.ini"
    parser = ConfigParser()

    save_section_values(config_path, parser, "CEye", {"token": None})

    loaded = ConfigParser()
    loaded.read(config_path)
    assert loaded.has_section("CEye")
    assert not loaded.has_option("CEye", "token")
