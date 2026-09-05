"""Tests for the OFX collection system.

Covers: version checking, manager lifecycle,
and workflow search integration.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

class TestSemver:
    """Tests for the lightweight semver helpers in manager.py."""

    def test_parse_basic(self):
        from ofx.collections.manager import _parse_semver

        assert _parse_semver("1.2.3") == (1, 2, 3, "")
        assert _parse_semver("0.0.0") == (0, 0, 0, "")
        assert _parse_semver("v2.1.0") == (2, 1, 0, "")

    def test_parse_prerelease(self):
        from ofx.collections.manager import _parse_semver

        assert _parse_semver("1.0.0-alpha") == (1, 0, 0, "alpha")
        assert _parse_semver("1.0.0-rc.1") == (1, 0, 0, "rc.1")

    def test_cmp(self):
        from ofx.collections.manager import _semver_cmp

        assert _semver_cmp("1.0.0", "0.9.9") == 1
        assert _semver_cmp("1.0.0", "1.0.0") == 0
        assert _semver_cmp("0.1.0", "0.2.0") == -1
        assert _semver_cmp("1.0.0-alpha", "1.0.0") == -1

    def test_check_constraint_gte(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.2.0", ">=1.0.0")
        assert check_version_constraint("1.0.0", ">=1.0.0")
        assert not check_version_constraint("0.9.9", ">=1.0.0")

    def test_check_constraint_lt(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("0.9.0", "<1.0.0")
        assert not check_version_constraint("1.0.0", "<1.0.0")

    def test_check_constraint_eq(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.0", "==1.0.0")
        assert not check_version_constraint("1.0.1", "==1.0.0")

    def test_check_constraint_neq(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.1", "!=1.0.0")
        assert not check_version_constraint("1.0.0", "!=1.0.0")

    def test_check_constraint_empty(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("anything", "")

    def test_check_bare_version(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.0", "1.0.0")
        assert not check_version_constraint("1.0.1", "1.0.0")

    def test_check_constraint_compatible_release(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.2.0", "~=1.2.0")
        assert check_version_constraint("1.9.9", "~=1.2.0")
        assert not check_version_constraint("2.0.0", "~=1.2.0")
        assert not check_version_constraint("1.1.9", "~=1.2.0")

    def test_check_constraint_gt(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.1", ">1.0.0")
        assert not check_version_constraint("1.0.0", ">1.0.0")
        assert not check_version_constraint("0.9.0", ">1.0.0")

    def test_check_constraint_lte(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.0", "<=1.0.0")
        assert check_version_constraint("0.5.0", "<=1.0.0")
        assert not check_version_constraint("1.0.1", "<=1.0.0")

    def test_cmp_prerelease_ordering(self):
        from ofx.collections.manager import _semver_cmp

        assert _semver_cmp("1.0.0-alpha", "1.0.0") == -1
        assert _semver_cmp("1.0.0", "1.0.0-alpha") == 1
        assert _semver_cmp("1.0.0-alpha", "1.0.0-beta") == -1

    def test_parse_malformed_version(self):
        from ofx.collections.manager import _parse_semver

        result = _parse_semver("1.0")
        assert result == (0, 0, 0, "")

    def test_constraint_with_spaces(self):
        from ofx.collections.manager import check_version_constraint

        assert check_version_constraint("1.0.0", ">= 1.0.0")
        assert check_version_constraint("1.0.0", "== 1.0.0")

class TestInstalledCollection:
    """Tests for installed-collection metadata model."""

    def test_defaults(self):
        from ofx.collections.manifest import InstalledCollection

        ic = InstalledCollection(name="test")
        assert ic.version == "0.0.0"
        assert ic.source == ""
        assert ic.installed_at

    def test_round_trip(self):
        from ofx.collections.manifest import InstalledCollection

        ic = InstalledCollection(
            name="demo",
            version="1.0.0",
            source="https://github.com/ofx-workflows/demo",
            path="/tmp/demo",
            tags=["recon"],
        )
        data = ic.model_dump()
        restored = InstalledCollection.model_validate(data)
        assert restored.name == ic.name
        assert restored.version == ic.version

class TestCollectionManager:
    """Tests for the core manager lifecycle (without real git clones)."""

    @pytest.fixture()
    def mgr(self, tmp_path: Path):
        from ofx.collections.manager import CollectionManager

        return CollectionManager(base_dir=tmp_path)

    def test_empty_registry(self, mgr):
        assert mgr.list_installed() == {}

    def test_manual_install_and_list(self, mgr, tmp_path):
        """Simulate what add() does after cloning, without hitting git."""
        from ofx.collections.manifest import InstalledCollection

        coll_dir = tmp_path / "my-coll"
        coll_dir.mkdir()
        (coll_dir / "scan.yaml").write_text("name: scan\n")

        entry = InstalledCollection(
            name="my-coll",
            source="https://github.com/ofx-workflows/my-coll",
            path=str(coll_dir),
        )
        mgr._installed["my-coll"] = entry
        mgr._save_installed()

        from ofx.collections.manager import CollectionManager

        mgr2 = CollectionManager(base_dir=tmp_path)
        assert "my-coll" in mgr2.list_installed()

    def test_remove(self, mgr, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        coll_dir = tmp_path / "removeme"
        coll_dir.mkdir()
        (coll_dir / "file.txt").write_text("data")

        mgr._installed["removeme"] = InstalledCollection(
            name="removeme", path=str(coll_dir)
        )
        mgr._save_installed()

        assert mgr.remove("removeme")
        assert not coll_dir.exists()
        assert mgr.get("removeme") is None

    def test_remove_nonexistent(self, mgr):
        assert not mgr.remove("ghost")

    def test_info(self, mgr, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        d = tmp_path / "info-test"
        d.mkdir()
        mgr._installed["info-test"] = InstalledCollection(name="info-test", path=str(d))
        entry = mgr.info("info-test")
        assert entry is not None
        assert entry.name == "info-test"

    def test_collection_workflow_dirs(self, mgr, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        d = tmp_path / "wf-dir"
        d.mkdir()
        mgr._installed["wf-dir"] = InstalledCollection(name="wf-dir", path=str(d))
        dirs = mgr.collection_workflow_dirs()
        assert len(dirs) == 1
        assert dirs[0] == d

    def test_migrate_from_assets(self, mgr, tmp_path):
        legacy_dir = tmp_path / "legacy-coll"
        legacy_dir.mkdir()
        (legacy_dir / "action.yml").write_text("name: action\n")

        assets_file = tmp_path / "assets.json"
        assets_file.write_text(
            json.dumps(
                {
                    "legacy-coll": {
                        "path": str(legacy_dir),
                        "url": "https://example.com/repo",
                    }
                }
            )
        )

        count = mgr.migrate_from_assets(assets_file)
        assert count == 1
        assert "legacy-coll" in mgr.list_installed()

    def test_migrate_idempotent(self, mgr, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        mgr._installed["already"] = InstalledCollection(name="already", path="/nope")
        assets_file = tmp_path / "assets.json"
        assets_file.write_text(json.dumps({"already": {"path": "/nope"}}))

        assert mgr.migrate_from_assets(assets_file) == 0

class TestWorkflowSearchIntegration:
    """Verify that get_workflow_search_dirs() picks up integration directories."""

    def test_exegol_workspace_and_resources_precede_tool_defaults(
        self, tmp_path: Path, monkeypatch
    ):
        import ofx.settings as s
        from ofx.commands.project.project_manager import ProjectManager

        workspace = tmp_path / "workspace"
        resources = tmp_path / "resources"
        defaults = tmp_path / "defaults"
        monkeypatch.setenv("EXEGOL_WORKSPACE_ROOT", str(workspace))
        monkeypatch.setenv("EXEGOL_RESOURCES", str(resources))
        monkeypatch.setattr(s, "DEFAULT_WORKFLOWS_DIRS", [defaults])
        monkeypatch.setattr(s, "COLLECTIONS_DIR", tmp_path / "missing")
        monkeypatch.setattr(
            ProjectManager, "get_project_workflow_dir", staticmethod(lambda: None)
        )

        assert s.get_workflow_search_dirs() == [
            workspace / "workflows",
            resources / "integrations" / "ofx" / "workflows",
            defaults,
        ]

    def test_includes_collection_dirs(self, tmp_path: Path, monkeypatch):
        """Collections directory is scanned and added to search dirs."""
        coll_a = tmp_path / "collections" / "coll-a"
        coll_b = tmp_path / "collections" / "coll-b"
        coll_a.mkdir(parents=True)
        coll_b.mkdir(parents=True)
        (tmp_path / "collections" / "installed.json").write_text("{}")

        import ofx.settings as s

        monkeypatch.setattr(s, "COLLECTIONS_DIR", tmp_path / "collections")
        monkeypatch.setattr(s, "DEFAULT_WORKFLOWS_DIRS", [tmp_path / "workflows"])

        dirs = s.get_workflow_search_dirs()
        dir_names = [d.name for d in dirs]
        assert "coll-a" in dir_names
        assert "coll-b" in dir_names
        assert "installed.json" not in dir_names

    def test_empty_collections_dir(self, tmp_path: Path, monkeypatch):
        """When no collections are installed, only default dirs + built-in workflow dirs are returned."""
        import ofx.settings as s
        from ofx.commands.project.project_manager import ProjectManager

        monkeypatch.setattr(s, "COLLECTIONS_DIR", tmp_path / "empty")
        monkeypatch.setattr(s, "DEFAULT_WORKFLOWS_DIRS", [tmp_path / "wf"])
        monkeypatch.setattr(
            ProjectManager, "get_project_workflow_dir", staticmethod(lambda: None)
        )

        dirs = s.get_workflow_search_dirs()
        assert dirs[0] == tmp_path / "wf"
        assert len(dirs) >= 1
