"""Tests for the `ofx project use` command."""

import json
import os
import subprocess
from pathlib import Path

import pytest

import ofx.settings as settings_mod

# Helper to locate the temporary config file location used by the CLI (HOME is monkey‑patched)
def _config_path(tmp_home: Path) -> Path:
    return tmp_home / ".ofx" / "config.json"

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
    cfg = json.loads(_config_path(temp_home).read_text())
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
    cfg_after = json.loads(_config_path(temp_home).read_text())
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
