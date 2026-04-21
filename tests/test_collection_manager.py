"""Tests for CollectionManager: semver helpers, CRUD, migration, and query methods."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ofx.collections.manager import (
    CollectionManager,
    _parse_semver,
    _semver_cmp,
    check_version_constraint,
)

# ── Semver parsing ───────────────────────────────────────────────────────


class TestParseSemver:
    def test_basic(self):
        assert _parse_semver("1.2.3") == (1, 2, 3, "")

    def test_with_v_prefix(self):
        assert _parse_semver("v1.2.3") == (1, 2, 3, "")

    def test_with_pre_release(self):
        assert _parse_semver("1.0.0-alpha") == (1, 0, 0, "alpha")

    def test_with_build_metadata(self):
        assert _parse_semver("1.0.0+build.123") == (1, 0, 0, "")

    def test_with_pre_and_build(self):
        assert _parse_semver("2.1.0-rc.1+build.42") == (2, 1, 0, "rc.1")

    def test_invalid(self):
        assert _parse_semver("not-a-version") == (0, 0, 0, "")

    def test_leading_whitespace(self):
        assert _parse_semver("  v1.2.3 ") == (1, 2, 3, "")


# ── Semver comparison ────────────────────────────────────────────────────


class TestSemverCmp:
    def test_equal(self):
        assert _semver_cmp("1.0.0", "1.0.0") == 0

    def test_major_diff(self):
        assert _semver_cmp("2.0.0", "1.0.0") == 1
        assert _semver_cmp("1.0.0", "2.0.0") == -1

    def test_minor_diff(self):
        assert _semver_cmp("1.2.0", "1.1.0") == 1
        assert _semver_cmp("1.1.0", "1.2.0") == -1

    def test_patch_diff(self):
        assert _semver_cmp("1.0.2", "1.0.1") == 1
        assert _semver_cmp("1.0.1", "1.0.2") == -1

    def test_pre_release_less_than_release(self):
        assert _semver_cmp("1.0.0-alpha", "1.0.0") == -1

    def test_release_greater_than_pre(self):
        assert _semver_cmp("1.0.0", "1.0.0-beta") == 1

    def test_pre_release_comparison(self):
        assert _semver_cmp("1.0.0-alpha", "1.0.0-beta") == -1
        assert _semver_cmp("1.0.0-beta", "1.0.0-alpha") == 1

    def test_same_pre(self):
        assert _semver_cmp("1.0.0-rc.1", "1.0.0-rc.1") == 0


# ── Version constraint checking ──────────────────────────────────────────


class TestCheckVersionConstraint:
    def test_empty_constraint(self):
        assert check_version_constraint("1.0.0", "") is True

    def test_gte(self):
        assert check_version_constraint("1.2.0", ">=1.0.0") is True
        assert check_version_constraint("1.0.0", ">=1.0.0") is True
        assert check_version_constraint("0.9.0", ">=1.0.0") is False

    def test_gt(self):
        assert check_version_constraint("1.1.0", ">1.0.0") is True
        assert check_version_constraint("1.0.0", ">1.0.0") is False

    def test_lte(self):
        assert check_version_constraint("1.0.0", "<=1.0.0") is True
        assert check_version_constraint("0.9.0", "<=1.0.0") is True
        assert check_version_constraint("1.1.0", "<=1.0.0") is False

    def test_lt(self):
        assert check_version_constraint("0.9.0", "<1.0.0") is True
        assert check_version_constraint("1.0.0", "<1.0.0") is False

    def test_eq(self):
        assert check_version_constraint("1.0.0", "==1.0.0") is True
        assert check_version_constraint("1.0.1", "==1.0.0") is False

    def test_neq(self):
        assert check_version_constraint("1.0.1", "!=1.0.0") is True
        assert check_version_constraint("1.0.0", "!=1.0.0") is False

    def test_compatible(self):
        assert check_version_constraint("1.2.0", "~=1.0.0") is True
        assert check_version_constraint("1.9.9", "~=1.0.0") is True
        assert check_version_constraint("2.0.0", "~=1.0.0") is False
        assert check_version_constraint("0.9.0", "~=1.0.0") is False

    def test_bare_version(self):
        assert check_version_constraint("1.0.0", "1.0.0") is True
        assert check_version_constraint("1.0.1", "1.0.0") is False


# ── CollectionManager ────────────────────────────────────────────────────


class TestCollectionManager:
    @pytest.fixture
    def mgr(self, tmp_path):
        return CollectionManager(base_dir=tmp_path)

    def test_empty_initial_state(self, mgr):
        assert mgr.list_installed() == {}

    def test_load_installed_empty_file(self, tmp_path):
        (tmp_path / "installed.json").write_text("{}")
        mgr = CollectionManager(base_dir=tmp_path)
        assert mgr.list_installed() == {}

    def test_load_installed_corrupt_json(self, tmp_path):
        (tmp_path / "installed.json").write_text("not json")
        mgr = CollectionManager(base_dir=tmp_path)
        assert mgr.list_installed() == {}

    def test_save_and_reload(self, tmp_path):
        mgr = CollectionManager(base_dir=tmp_path)
        # Manually insert an entry
        from ofx.collections.manifest import InstalledCollection
        entry = InstalledCollection(
            name="test-coll",
            source="https://github.com/example/test-coll",
            pinned_ref="abc123",
            path=str(tmp_path / "test-coll"),
        )
        mgr._installed["test-coll"] = entry
        mgr._save_installed()

        # Reload
        mgr2 = CollectionManager(base_dir=tmp_path)
        assert "test-coll" in mgr2.list_installed()
        assert mgr2.get("test-coll").name == "test-coll"

    def test_get_returns_none_for_missing(self, mgr):
        assert mgr.get("nonexistent") is None

    def test_info_returns_none_for_missing(self, mgr):
        assert mgr.info("nonexistent") is None

    def test_remove_nonexistent(self, mgr):
        assert mgr.remove("nonexistent") is False

    def test_remove_installed(self, tmp_path):
        from ofx.collections.manifest import InstalledCollection
        coll_dir = tmp_path / "my-coll"
        coll_dir.mkdir()
        (coll_dir / "test.yaml").write_text("name: test")

        mgr = CollectionManager(base_dir=tmp_path)
        entry = InstalledCollection(
            name="my-coll",
            source="local",
            pinned_ref="HEAD",
            path=str(coll_dir),
        )
        mgr._installed["my-coll"] = entry
        mgr._save_installed()

        assert mgr.remove("my-coll") is True
        assert "my-coll" not in mgr.list_installed()
        assert not coll_dir.exists()

    def test_collection_workflow_dirs(self, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        coll_dir = tmp_path / "recon"
        coll_dir.mkdir()

        mgr = CollectionManager(base_dir=tmp_path)
        mgr._installed["recon"] = InstalledCollection(
            name="recon",
            source="local",
            pinned_ref="abc",
            path=str(coll_dir),
        )

        dirs = mgr.collection_workflow_dirs()
        assert len(dirs) == 1
        assert dirs[0] == coll_dir

    def test_collection_workflow_dirs_skips_missing(self, tmp_path):
        from ofx.collections.manifest import InstalledCollection

        mgr = CollectionManager(base_dir=tmp_path)
        mgr._installed["gone"] = InstalledCollection(
            name="gone",
            source="local",
            pinned_ref="abc",
            path=str(tmp_path / "gone"),  # doesn't exist
        )
        assert mgr.collection_workflow_dirs() == []

    def test_add_raises_for_duplicate(self, tmp_path):
        from ofx.collections.manifest import InstalledCollection
        mgr = CollectionManager(base_dir=tmp_path)
        mgr._installed["existing"] = InstalledCollection(
            name="existing", source="url", pinned_ref="x", path=str(tmp_path / "existing"),
        )
        with pytest.raises(ValueError, match="already installed"):
            mgr.add("https://github.com/example/existing")

    def test_add_raises_for_existing_dir(self, tmp_path):
        mgr = CollectionManager(base_dir=tmp_path)
        (tmp_path / "my-repo").mkdir()
        with pytest.raises(ValueError, match="already exists"):
            mgr.add("https://github.com/example/my-repo")


# ── Migration ────────────────────────────────────────────────────────────


class TestMigration:
    def test_migrate_missing_file(self, tmp_path):
        mgr = CollectionManager(base_dir=tmp_path)
        assert mgr.migrate_from_assets(tmp_path / "nope.json") == 0

    def test_migrate_corrupt_file(self, tmp_path):
        assets = tmp_path / "assets.json"
        assets.write_text("{bad json")
        mgr = CollectionManager(base_dir=tmp_path)
        assert mgr.migrate_from_assets(assets) == 0

    def test_migrate_skips_already_installed(self, tmp_path):
        from ofx.collections.manifest import InstalledCollection
        mgr = CollectionManager(base_dir=tmp_path)
        mgr._installed["existing"] = InstalledCollection(
            name="existing", source="u", pinned_ref="x", path=str(tmp_path / "existing"),
        )

        coll_dir = tmp_path / "existing"
        coll_dir.mkdir()
        assets = tmp_path / "assets.json"
        assets.write_text(json.dumps({"existing": {"path": str(coll_dir), "url": "u"}}))
        assert mgr.migrate_from_assets(assets) == 0

    def test_migrate_skips_missing_path(self, tmp_path):
        mgr = CollectionManager(base_dir=tmp_path)
        assets = tmp_path / "assets.json"
        assets.write_text(json.dumps({"gone": {"path": "/nonexistent", "url": "u"}}))
        assert mgr.migrate_from_assets(assets) == 0


# ── Authenticated URL ────────────────────────────────────────────────────


class TestAuthenticatedUrl:
    def test_no_token(self):
        with patch("ofx.collections.manager.CollectionManager._authenticated_url.__wrapped__", create=True):
            pass
        # Direct call
        with patch("ofx.settings.get_github_token", return_value=""):
            result = CollectionManager._authenticated_url("https://github.com/org/repo")
            assert result == "https://github.com/org/repo"

    def test_with_token(self):
        with patch("ofx.settings.get_github_token", return_value="ghp_testtoken"):
            result = CollectionManager._authenticated_url("https://github.com/org/repo")
            assert "x-access-token:ghp_testtoken@github.com" in result

    def test_non_github_url_unchanged(self):
        with patch("ofx.settings.get_github_token", return_value="ghp_testtoken"):
            result = CollectionManager._authenticated_url("https://gitlab.com/org/repo")
            assert result == "https://gitlab.com/org/repo"
