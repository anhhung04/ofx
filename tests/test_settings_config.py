"""Tests for settings.py config helpers: update_config_field, _dump_default_config, _ensure_default_config."""

from __future__ import annotations

import threading

import pytest
import yaml


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect CONFIG_YAML and BASE_DATA_DIR to a tmp dir for each test."""
    import ofx.settings as sm

    cfg = tmp_path / "config.yml"
    monkeypatch.setattr(sm, "CONFIG_YAML", cfg)
    monkeypatch.setattr(sm, "BASE_DATA_DIR", tmp_path)
    return cfg


# ---------------------------------------------------------------------------
# update_config_field
# ---------------------------------------------------------------------------


class TestUpdateConfigField:
    def test_creates_config_when_missing(self, isolated_config):
        from ofx.settings import update_config_field

        assert not isolated_config.exists()
        update_config_field("active_project", "myproj")
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert data["active_project"] == "myproj"

    def test_updates_existing_key(self, isolated_config):
        from ofx.settings import update_config_field

        isolated_config.write_text("active_project: old\n")
        update_config_field("active_project", "new")
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert data["active_project"] == "new"

    def test_preserves_other_keys(self, isolated_config):
        from ofx.settings import update_config_field

        isolated_config.write_text("debug: true\nsome_key: some_value\n")
        update_config_field("active_project", "proj")
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert data["active_project"] == "proj"
        assert data["debug"] is True
        assert data["some_key"] == "some_value"

    def test_removes_key_when_value_is_none(self, isolated_config):
        from ofx.settings import update_config_field

        isolated_config.write_text("active_project: toremove\nother: keep\n")
        update_config_field("active_project", None)
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert "active_project" not in data
        assert data["other"] == "keep"

    def test_no_op_remove_missing_key(self, isolated_config):
        """Removing a key that doesn't exist is a no-op (no error)."""
        from ofx.settings import update_config_field

        isolated_config.write_text("other: 1\n")
        update_config_field("active_project", None)  # should not raise
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert "active_project" not in data

    def test_handles_corrupted_yaml_gracefully(self, isolated_config):
        from ofx.settings import update_config_field

        isolated_config.write_text("not: valid: yaml: {{{{")
        # Should not raise; should start fresh
        update_config_field("active_project", "safe")
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert data["active_project"] == "safe"

    def test_atomic_write(self, isolated_config):
        """The tmp file should be gone after a successful write."""
        from ofx.settings import update_config_field

        update_config_field("key", "val")
        tmp_files = list(isolated_config.parent.glob(".config_tmp_*"))
        assert tmp_files == [], f"Temp file not cleaned up: {tmp_files}"

    def test_concurrent_writes_are_safe(self, isolated_config):
        """Multiple threads writing simultaneously should not corrupt the file."""
        from ofx.settings import update_config_field

        errors: list[Exception] = []

        def _writer(idx: int) -> None:
            try:
                update_config_field(f"key_{idx}", f"val_{idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent writes: {errors}"

        data = yaml.safe_load(isolated_config.read_text()) or {}
        # All 10 keys should be present
        for i in range(10):
            assert f"key_{i}" in data, f"key_{i} missing from config"


# ---------------------------------------------------------------------------
# _dump_default_config
# ---------------------------------------------------------------------------


class TestDumpDefaultConfig:
    def test_returns_yaml_string_with_header(self):
        from ofx.settings import _CONFIG_YAML_HEADER, _dump_default_config

        result = _dump_default_config()
        assert result.startswith(_CONFIG_YAML_HEADER)
        # Should be valid YAML after the header
        body = result[len(_CONFIG_YAML_HEADER) :]
        data = yaml.safe_load(body)
        assert isinstance(data, dict)

    def test_excludes_active_project(self):
        from ofx.settings import _dump_default_config

        result = _dump_default_config()
        data = yaml.safe_load(result) or {}
        assert "active_project" not in data

    def test_excludes_other_excluded_fields(self):
        from ofx.settings import _CONFIG_EXCLUDE_FIELDS, _dump_default_config

        result = _dump_default_config()
        data = yaml.safe_load(result) or {}
        for field in _CONFIG_EXCLUDE_FIELDS:
            assert field not in data


# ---------------------------------------------------------------------------
# _ensure_default_config
# ---------------------------------------------------------------------------


class TestEnsureDefaultConfig:
    def test_creates_config_when_missing(self, isolated_config):
        from ofx.settings import _ensure_default_config

        assert not isolated_config.exists()
        _ensure_default_config()
        assert isolated_config.exists()
        data = yaml.safe_load(isolated_config.read_text())
        assert isinstance(data, dict)

    def test_does_not_overwrite_existing(self, isolated_config):
        from ofx.settings import _ensure_default_config

        isolated_config.write_text("custom_key: custom_value\n")
        _ensure_default_config()
        data = yaml.safe_load(isolated_config.read_text()) or {}
        assert data.get("custom_key") == "custom_value"
