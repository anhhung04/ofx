"""Tests for the `ofx project use` command."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

import ofx.settings as settings_mod


# Helper to locate the temporary config file location used by the CLI (HOME is monkey‑patched)
def _config_path(tmp_home: Path) -> Path:
    return tmp_home / ".ofx" / "config.yml"

@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    # Point HOME to a temporary directory so the CLI writes config there
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    projects_dir = home / ".ofx" / "projects"
    projects_dir.mkdir(parents=True)
    os.environ["OFX_PROJECTS_PATH"] = str(projects_dir)
    monkeypatch.setattr(settings_mod, "DEFAULT_PROJECTS_PATH", projects_dir)
    return home

def test_use_set_and_clear(temp_home, monkeypatch, tmp_path):
    # Create a dummy project using the ProjectManager helper
    from ofx.commands.project.project_manager import ProjectManager
    proj_name = "myproj"
    ProjectManager.create_project(proj_name)

    # 1️⃣ Set active project
    env = os.environ.copy()
    env["HOME"] = str(temp_home)
    env["OFX_PROJECTS_PATH"] = str(temp_home / ".ofx" / "projects")
    result_set = subprocess.run(
        ["uv", "run", "ofx", "project", "use", proj_name],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_set.returncode == 0, f"CLI failed: {result_set.stderr}"
    cfg = yaml.safe_load(_config_path(temp_home).read_text()) or {}
    assert cfg.get("active_project") == proj_name
    assert "Active project set to" in result_set.stdout

    # 2️⃣ Clear active project
    result_clear = subprocess.run(
        ["uv", "run", "ofx", "project", "use", "--clear"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_clear.returncode == 0, f"CLI clear failed: {result_clear.stderr}"
    cfg_after = yaml.safe_load(_config_path(temp_home).read_text()) or {}
    assert "active_project" not in cfg_after
    assert "Active project cleared" in result_clear.stdout

def test_use_invalid_project(temp_home, tmp_path):
    # Attempt to set a non‑existent project
    result = subprocess.run(
        ["uv", "run", "ofx", "project", "use", "nosuchproj"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "CLI should have exited with error for missing project"
    assert "Project 'nosuchproj' not found" in result.stdout or "Project 'nosuchproj' not found" in result.stderr


def test_migrate_json_config(temp_home, monkeypatch):
    """Legacy config.json active_project is migrated to config.yml on import."""
    import json

    import yaml

    ofx_dir = temp_home / ".ofx"
    ofx_dir.mkdir(parents=True, exist_ok=True)

    # Write a legacy config.json
    (ofx_dir / "config.json").write_text(json.dumps({"active_project": "legacyproj"}))

    # Patch BASE_DATA_DIR so the migration targets temp_home
    import ofx.settings as sm
    monkeypatch.setattr(sm, "BASE_DATA_DIR", ofx_dir)
    monkeypatch.setattr(sm, "CONFIG_YAML", ofx_dir / "config.yml")

    # Run the migration directly
    sm._migrate_json_config()

    # config.json should be gone
    assert not (ofx_dir / "config.json").exists()

    # config.yml should contain active_project
    cfg = yaml.safe_load((ofx_dir / "config.yml").read_text()) or {}
    assert cfg.get("active_project") == "legacyproj"


def test_migrate_json_config_no_overwrite(temp_home, monkeypatch):
    """Migration does not overwrite an active_project already set in config.yml."""
    import json

    import yaml

    ofx_dir = temp_home / ".ofx"
    ofx_dir.mkdir(parents=True, exist_ok=True)

    # Pre-existing config.yml already has active_project
    (ofx_dir / "config.yml").write_text("active_project: existingproj\n")
    # Legacy config.json has a different value
    (ofx_dir / "config.json").write_text(json.dumps({"active_project": "legacyproj"}))

    import ofx.settings as sm
    monkeypatch.setattr(sm, "BASE_DATA_DIR", ofx_dir)
    monkeypatch.setattr(sm, "CONFIG_YAML", ofx_dir / "config.yml")

    sm._migrate_json_config()

    # config.json cleaned up
    assert not (ofx_dir / "config.json").exists()

    # config.yml still has the original value
    cfg = yaml.safe_load((ofx_dir / "config.yml").read_text()) or {}
    assert cfg.get("active_project") == "existingproj"
