"""Tests for the OFX collection system.

Covers: manifest parsing, version checking, manager lifecycle,
auto-discovery, dependency resolution, and workflow search integration.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Semver / version constraint helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# CollectionManifest
# ---------------------------------------------------------------------------


class TestCollectionManifest:
    """Tests for manifest model and discovery."""

    def test_from_yaml(self, tmp_path: Path):
        from ofx.collections.manifest import CollectionManifest

        manifest_file = tmp_path / "collection.yaml"
        manifest_file.write_text(
            textwrap.dedent("""\
            name: my-collection
            version: "1.2.0"
            description: Test collection
            author: tester
            license: MIT
            tags:
              - recon
              - enumeration
            workflows:
              - scan.yaml
              - enum.yaml
            tools:
              - nmap
            dependencies:
              - name: helpers
                version: ">=0.1.0"
            """)
        )

        m = CollectionManifest.from_yaml(manifest_file)
        assert m.name == "my-collection"
        assert m.version == "1.2.0"
        assert m.description == "Test collection"
        assert m.author == "tester"
        assert m.license == "MIT"
        assert m.tags == ["recon", "enumeration"]
        assert m.workflows == ["scan.yaml", "enum.yaml"]
        assert m.tools == ["nmap"]
        assert len(m.dependencies) == 1
        assert m.dependencies[0].name == "helpers"
        assert m.dependencies[0].version == ">=0.1.0"

    def test_from_directory_with_manifest(self, tmp_path: Path):
        from ofx.collections.manifest import CollectionManifest

        (tmp_path / "collection.yaml").write_text("name: explicit\nversion: '2.0.0'\n")
        (tmp_path / "wf1.yaml").write_text("name: wf1\n")
        (tmp_path / "wf2.yml").write_text("name: wf2\n")

        m = CollectionManifest.from_directory(tmp_path)
        assert m.name == "explicit"
        assert m.version == "2.0.0"
        # workflows auto-discovered since manifest has empty list
        assert sorted(m.workflows) == ["wf1.yaml", "wf2.yml"]

    def test_from_directory_no_manifest(self, tmp_path: Path):
        from ofx.collections.manifest import CollectionManifest

        (tmp_path / "action.yml").write_text("name: action\n")
        (tmp_path / "helper.yaml").write_text("name: helper\n")

        m = CollectionManifest.from_directory(tmp_path)
        assert m.name == tmp_path.name
        assert sorted(m.workflows) == ["action.yml", "helper.yaml"]

    def test_auto_discover_skips_collection_yaml(self, tmp_path: Path):
        from ofx.collections.manifest import CollectionManifest

        (tmp_path / "collection.yaml").write_text("name: test\n")
        (tmp_path / "real-workflow.yaml").write_text("name: wf\n")

        m = CollectionManifest.from_directory(tmp_path)
        assert "collection.yaml" not in m.workflows
        assert "real-workflow.yaml" in m.workflows

    def test_explicit_workflows_not_overridden(self, tmp_path: Path):
        from ofx.collections.manifest import CollectionManifest

        (tmp_path / "collection.yaml").write_text(
            "name: pinned\nworkflows:\n  - only-this.yaml\n"
        )
        (tmp_path / "only-this.yaml").write_text("name: x\n")
        (tmp_path / "ignored.yaml").write_text("name: y\n")

        m = CollectionManifest.from_directory(tmp_path)
        assert m.workflows == ["only-this.yaml"]


# ---------------------------------------------------------------------------
# InstalledCollection
# ---------------------------------------------------------------------------


class TestInstalledCollection:
    """Tests for installed-collection metadata model."""

    def test_defaults(self):
        from ofx.collections.manifest import InstalledCollection

        ic = InstalledCollection(name="test")
        assert ic.version == "0.0.0"
        assert ic.source == ""
        assert ic.installed_at  # auto-filled

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




# ---------------------------------------------------------------------------
# CollectionManager
# ---------------------------------------------------------------------------


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
        from ofx.collections.manifest import CollectionManifest, InstalledCollection

        coll_dir = tmp_path / "my-coll"
        coll_dir.mkdir()
        (coll_dir / "collection.yaml").write_text(
            "name: my-coll\nversion: '1.0.0'\ndescription: test\n"
        )
        (coll_dir / "scan.yaml").write_text("name: scan\n")

        manifest = CollectionManifest.from_directory(coll_dir)
        entry = InstalledCollection(
            name="my-coll",
            version=manifest.version,
            source="https://github.com/ofx-workflows/my-coll",
            path=str(coll_dir),
            description=manifest.description,
        )
        mgr._installed["my-coll"] = entry
        mgr._save_installed()

        # Reload and check
        from ofx.collections.manager import CollectionManager

        mgr2 = CollectionManager(base_dir=tmp_path)
        assert "my-coll" in mgr2.list_installed()
        assert mgr2.get("my-coll").version == "1.0.0"

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
        (d / "collection.yaml").write_text(
            "name: info-test\nversion: '0.5.0'\nauthor: dev\n"
        )
        mgr._installed["info-test"] = InstalledCollection(
            name="info-test", path=str(d)
        )
        m = mgr.info("info-test")
        assert m is not None
        assert m.version == "0.5.0"
        assert m.author == "dev"

    def test_collection_workflow_dirs(self, mgr, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        d = tmp_path / "wf-dir"
        d.mkdir()
        mgr._installed["wf-dir"] = InstalledCollection(
            name="wf-dir", path=str(d)
        )
        dirs = mgr.collection_workflow_dirs()
        assert len(dirs) == 1
        assert dirs[0] == d

    def test_migrate_from_assets(self, mgr, tmp_path):
        # Create a fake legacy asset directory
        legacy_dir = tmp_path / "legacy-coll"
        legacy_dir.mkdir()
        (legacy_dir / "action.yml").write_text("name: action\n")

        assets_file = tmp_path / "assets.json"
        assets_file.write_text(
            json.dumps({"legacy-coll": {"path": str(legacy_dir), "url": "https://example.com/repo"}})
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


# ---------------------------------------------------------------------------
# Workflow search integration
# ---------------------------------------------------------------------------


class TestWorkflowSearchIntegration:
    """Verify that get_workflow_search_dirs() picks up collection directories."""

    def test_includes_collection_dirs(self, tmp_path: Path, monkeypatch):
        """Collections directory is scanned and added to search dirs."""
        # Create fake collection dirs
        coll_a = tmp_path / "collections" / "coll-a"
        coll_b = tmp_path / "collections" / "coll-b"
        coll_a.mkdir(parents=True)
        coll_b.mkdir(parents=True)
        # random file — should be ignored (not a dir)
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

        monkeypatch.setattr(s, "COLLECTIONS_DIR", tmp_path / "empty")
        monkeypatch.setattr(s, "DEFAULT_WORKFLOWS_DIRS", [tmp_path / "wf"])

        dirs = s.get_workflow_search_dirs()
        # Should include default dir + built-in workflow subdirs
        assert dirs[0] == tmp_path / "wf"
        assert len(dirs) >= 1



