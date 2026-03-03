"""Tests for the OFX collection system.

Covers: manifest parsing, version checking, manager lifecycle,
auto-discovery, dependency resolution, workflow search integration,
and index client.
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
# CollectionIndex
# ---------------------------------------------------------------------------


class TestCollectionIndex:
    """Tests for the index model and search."""

    def test_search_by_name(self):
        from ofx.collections.manifest import CollectionIndex, CollectionIndexEntry

        idx = CollectionIndex(
            collections={
                "recon-tools": CollectionIndexEntry(
                    name="recon-tools",
                    description="Recon workflows",
                    tags=["recon"],
                ),
                "privesc": CollectionIndexEntry(
                    name="privesc",
                    description="Privilege escalation",
                    tags=["priv"],
                ),
            }
        )

        results = idx.search("recon")
        assert len(results) == 1
        assert results[0].name == "recon-tools"

    def test_search_by_tag(self):
        from ofx.collections.manifest import CollectionIndex, CollectionIndexEntry

        idx = CollectionIndex(
            collections={
                "c1": CollectionIndexEntry(name="c1", tags=["enum"]),
            }
        )
        assert len(idx.search("enum")) == 1

    def test_search_case_insensitive(self):
        from ofx.collections.manifest import CollectionIndex, CollectionIndexEntry

        idx = CollectionIndex(
            collections={
                "UpCase": CollectionIndexEntry(
                    name="UpCase", description="Mixed Case"
                ),
            }
        )
        assert len(idx.search("upcase")) == 1
        assert len(idx.search("mixed case")) == 1


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

    def test_resolve_source_bare_name(self):
        from ofx.collections.manager import CollectionManager

        assert (
            CollectionManager.resolve_source("recon-tools")
            == "https://github.com/ofx-workflows/recon-tools"
        )

    def test_resolve_source_org_repo(self):
        from ofx.collections.manager import CollectionManager

        assert (
            CollectionManager.resolve_source("myorg/myrepo")
            == "https://github.com/myorg/myrepo"
        )

    def test_resolve_source_full_url(self):
        from ofx.collections.manager import CollectionManager

        url = "https://gitlab.com/user/repo.git"
        assert CollectionManager.resolve_source(url) == url

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
        """When no collections are installed, only default dirs are returned."""
        import ofx.settings as s

        monkeypatch.setattr(s, "COLLECTIONS_DIR", tmp_path / "empty")
        monkeypatch.setattr(s, "DEFAULT_WORKFLOWS_DIRS", [tmp_path / "wf"])

        dirs = s.get_workflow_search_dirs()
        assert len(dirs) == 1
        assert dirs[0] == tmp_path / "wf"


# ---------------------------------------------------------------------------
# IndexClient
# ---------------------------------------------------------------------------


class TestIndexClient:
    """Tests for the index client (cached / offline only — no real HTTP)."""

    def test_load_cache(self, tmp_path: Path):
        from ofx.collections.index import IndexClient

        cache_file = tmp_path / "index.json"
        cache_file.write_text(
            json.dumps(
                {
                    "collections": {
                        "demo": {
                            "name": "demo",
                            "description": "Demo collection",
                            "latest": "1.0.0",
                            "tags": ["demo"],
                        }
                    }
                }
            )
        )

        client = IndexClient(cache_dir=tmp_path)
        # Force cache hit by ensuring file is fresh
        idx = client._load_cache()
        assert "demo" in idx.collections
        assert idx.collections["demo"].latest == "1.0.0"

    def test_search_cached(self, tmp_path: Path):
        from ofx.collections.index import IndexClient

        cache_file = tmp_path / "index.json"
        cache_file.write_text(
            json.dumps(
                {
                    "collections": {
                        "recon": {
                            "name": "recon",
                            "description": "Recon tools",
                            "tags": ["enum"],
                        },
                        "exploit": {
                            "name": "exploit",
                            "description": "Exploit pack",
                            "tags": ["exploit"],
                        },
                    }
                }
            )
        )

        client = IndexClient(cache_dir=tmp_path)
        results = client.search("recon", force_refresh=False)
        assert len(results) == 1
        assert results[0].name == "recon"

    def test_get_entry(self, tmp_path: Path):
        from ofx.collections.index import IndexClient

        cache_file = tmp_path / "index.json"
        cache_file.write_text(
            json.dumps(
                {
                    "collections": {
                        "my-coll": {
                            "name": "my-coll",
                            "source": "https://github.com/ofx-workflows/my-coll",
                        }
                    }
                }
            )
        )

        client = IndexClient(cache_dir=tmp_path)
        entry = client.get_entry("my-coll")
        assert entry is not None
        assert entry.source == "https://github.com/ofx-workflows/my-coll"

        assert client.get_entry("nonexistent") is None


class TestGitHubTokenResolution:
    """Tests for GitHub token auto-discovery via settings and gh CLI."""

    def test_get_github_token_from_settings(self, monkeypatch):
        """Explicit OFX_GITHUB_TOKEN takes priority over gh CLI."""
        from ofx import settings as settings_mod

        monkeypatch.setattr(settings_mod.settings, "github_token", "explicit-token")
        # Clear lru_cache so it doesn't use a stale value
        settings_mod._gh_cli_token.cache_clear()
        assert settings_mod.get_github_token() == "explicit-token"

    def test_get_github_token_falls_back_to_gh_cli(self, monkeypatch):
        """When no explicit token, falls back to gh auth token."""
        from ofx import settings as settings_mod

        monkeypatch.setattr(settings_mod.settings, "github_token", "")
        settings_mod._gh_cli_token.cache_clear()

        # Mock shutil.which to say gh exists
        monkeypatch.setattr(settings_mod.shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)

        # Mock subprocess.run to return a token
        class FakeResult:
            returncode = 0
            stdout = "  ghp_faketoken123\n"

        monkeypatch.setattr(
            settings_mod.subprocess,
            "run",
            lambda *a, **kw: FakeResult(),
        )

        assert settings_mod.get_github_token() == "ghp_faketoken123"
        settings_mod._gh_cli_token.cache_clear()

    def test_get_github_token_empty_when_no_gh(self, monkeypatch):
        """Returns empty string when gh is not installed and no env token."""
        from ofx import settings as settings_mod

        monkeypatch.setattr(settings_mod.settings, "github_token", "")
        settings_mod._gh_cli_token.cache_clear()
        monkeypatch.setattr(settings_mod.shutil, "which", lambda cmd: None)

        assert settings_mod.get_github_token() == ""
        settings_mod._gh_cli_token.cache_clear()

    def test_get_github_token_empty_when_gh_not_authed(self, monkeypatch):
        """Returns empty string when gh exists but is not authenticated."""
        from ofx import settings as settings_mod

        monkeypatch.setattr(settings_mod.settings, "github_token", "")
        settings_mod._gh_cli_token.cache_clear()
        monkeypatch.setattr(settings_mod.shutil, "which", lambda cmd: "/usr/bin/gh")

        class FakeResult:
            returncode = 1
            stdout = ""

        monkeypatch.setattr(
            settings_mod.subprocess,
            "run",
            lambda *a, **kw: FakeResult(),
        )

        assert settings_mod.get_github_token() == ""
        settings_mod._gh_cli_token.cache_clear()


class TestAuthenticatedUrl:
    """Tests for CollectionManager._authenticated_url."""

    def test_injects_token_into_github_https(self, monkeypatch):
        from ofx import settings as settings_mod
        from ofx.collections.manager import CollectionManager

        monkeypatch.setattr(settings_mod, "get_github_token", lambda: "ghp_test123")

        result = CollectionManager._authenticated_url(
            "https://github.com/ofx-workflows/recon-tools"
        )
        assert result == "https://x-access-token:ghp_test123@github.com/ofx-workflows/recon-tools"

    def test_no_token_returns_original(self, monkeypatch):
        from ofx import settings as settings_mod
        from ofx.collections.manager import CollectionManager

        monkeypatch.setattr(settings_mod, "get_github_token", lambda: "")

        url = "https://github.com/ofx-workflows/recon-tools"
        assert CollectionManager._authenticated_url(url) == url

    def test_non_github_url_unchanged(self, monkeypatch):
        from ofx import settings as settings_mod
        from ofx.collections.manager import CollectionManager

        monkeypatch.setattr(settings_mod, "get_github_token", lambda: "ghp_test123")

        url = "https://gitlab.com/my/repo"
        assert CollectionManager._authenticated_url(url) == url

    def test_ssh_url_unchanged(self, monkeypatch):
        from ofx import settings as settings_mod
        from ofx.collections.manager import CollectionManager

        monkeypatch.setattr(settings_mod, "get_github_token", lambda: "ghp_test123")

        url = "git@github.com:ofx-workflows/recon-tools.git"
        assert CollectionManager._authenticated_url(url) == url


class TestIndexClientAuth:
    """Tests for IndexClient token & URL resolution."""

    def test_explicit_token_used(self, tmp_path):
        from ofx.collections.index import IndexClient

        client = IndexClient(cache_dir=tmp_path, github_token="explicit-tok")
        headers = client._build_headers()
        assert headers["Authorization"] == "Bearer explicit-tok"

    def test_no_token_no_auth_header(self, tmp_path, monkeypatch):
        from ofx import settings as settings_mod
        from ofx.collections.index import IndexClient

        monkeypatch.setattr(settings_mod, "get_github_token", lambda: "")

        client = IndexClient(cache_dir=tmp_path)
        headers = client._build_headers()
        assert "Authorization" not in headers

    def test_resolve_index_url_raw_passthrough(self):
        from ofx.collections.index import _resolve_index_url

        url = "https://raw.githubusercontent.com/ofx-workflows/index/main/index.json"
        assert _resolve_index_url(url) == url

    def test_resolve_index_url_github_to_api(self):
        from ofx.collections.index import _resolve_index_url

        url = "https://github.com/myorg/private-index"
        result = _resolve_index_url(url)
        assert "api.github.com" in result
        assert "myorg" in result
        assert "private-index" in result

    def test_resolve_index_url_api_passthrough(self):
        from ofx.collections.index import _resolve_index_url

        url = "https://api.github.com/repos/myorg/index/contents/index.json?ref=main"
        assert _resolve_index_url(url) == url
