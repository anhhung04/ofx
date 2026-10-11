"""Tests for the `ofx project use` command."""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import ofx.settings as settings_mod
from ofx.commands.project.app import app
from ofx.commands.project.project_manager import ProjectManager

runner = CliRunner()


def _config_path(tmp_home: Path) -> Path:
    return tmp_home / ".ofx" / "config.yml"


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    projects_dir = home / ".ofx" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OFX_PROJECTS_PATH", str(projects_dir))
    monkeypatch.setattr(settings_mod, "CONFIG_YAML", _config_path(home))
    monkeypatch.setattr(settings_mod, "DEFAULT_PROJECTS_PATH", projects_dir)
    return home


def test_use_set_and_clear(temp_home):
    proj_name = "myproj"
    ProjectManager.create_project(proj_name)

    result_set = runner.invoke(app, ["use", proj_name])

    assert result_set.exit_code == 0
    cfg = yaml.safe_load(_config_path(temp_home).read_text()) or {}
    assert cfg.get("active_project") == proj_name
    assert "Active project set to" in result_set.output

    result_clear = runner.invoke(app, ["use", "--clear"])

    assert result_clear.exit_code == 0
    cfg_after = yaml.safe_load(_config_path(temp_home).read_text()) or {}
    assert "active_project" not in cfg_after
    assert "Active project cleared" in result_clear.output


def test_use_invalid_project(temp_home):
    result = runner.invoke(app, ["use", "nosuchproj"])

    assert result.exit_code == 1
    assert "Project 'nosuchproj' not found" in result.output


def test_create_project_uses_minimal_workspace_tree(tmp_path, monkeypatch):
    monkeypatch.setenv("OFX_PROJECTS_PATH", str(tmp_path))

    project = Path(ProjectManager.create_project("demo project"))

    assert {path.name for path in project.iterdir()} == {
        ".git",
        ".gitignore",
        "README.md",
        "evidence",
        "notes",
        "runs",
        "workflows",
    }
    assert "Rules of Engagement" in (project / "README.md").read_text()


class TestProjectInit:
    """`ofx project init` with --cwd/--use."""

    def test_init_requires_name_without_cwd(self, temp_home):
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1
        assert "Provide a project name or use --cwd" in result.output

    def test_init_cwd_defaults_to_dir_name(self, temp_home, monkeypatch):
        workdir = temp_home / "engagement-one"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        result = runner.invoke(app, ["init", "--cwd"], input="\n")

        assert result.exit_code == 0, result.output
        assert (workdir / "evidence").is_dir()
        assert (workdir / "workflows").is_dir()
        assert "engagement-one" in (workdir / "README.md").read_text()
        # nothing created under the default projects path
        assert list((temp_home / ".ofx" / "projects").iterdir()) == []

    def test_init_cwd_preserves_existing_gitignore(self, temp_home, monkeypatch):
        workdir = temp_home / "keepme"
        workdir.mkdir()
        (workdir / ".gitignore").write_text("my-secret-stuff/\n")
        monkeypatch.chdir(workdir)

        result = runner.invoke(app, ["init", "--cwd"], input="\n")

        assert result.exit_code == 0, result.output
        assert (workdir / ".gitignore").read_text() == "my-secret-stuff/\n"

    def test_init_cwd_use_sets_active_project_path(self, temp_home, monkeypatch):
        workdir = temp_home / "op"
        workdir.mkdir()
        monkeypatch.chdir(workdir)

        result = runner.invoke(app, ["init", "--cwd", "--use"], input="\n")

        assert result.exit_code == 0, result.output
        cfg = yaml.safe_load(_config_path(temp_home).read_text()) or {}
        # cwd projects can't resolve by name later — the path is stored
        assert cfg.get("active_project") == str(workdir)

    def test_init_use_sets_active_project_name(self, temp_home):
        result = runner.invoke(app, ["init", "named-proj", "--use"], input="\n")

        assert result.exit_code == 0, result.output
        cfg = yaml.safe_load(_config_path(temp_home).read_text()) or {}
        assert cfg.get("active_project") == "named-proj"
        assert (temp_home / ".ofx" / "projects" / "named-proj").is_dir()

    def test_init_without_use_leaves_active_project_unset(self, temp_home):
        result = runner.invoke(app, ["init", "plain-proj"], input="\n")

        assert result.exit_code == 0, result.output
        cfg_file = _config_path(temp_home)
        cfg = yaml.safe_load(cfg_file.read_text()) if cfg_file.exists() else {}
        assert not (cfg or {}).get("active_project")
