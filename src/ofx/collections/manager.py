"""Collection manager — add, remove, update, list installed collections."""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import git
from git.exc import GitCommandError

from ofx.collections.manifest import InstalledCollection
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

# ------------------------------------------------------------------
# Lightweight semver helpers (no external dependency)
# ------------------------------------------------------------------

_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z\-.]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
)


def _parse_semver(version: str) -> tuple[int, int, int, str]:
    """Parse a semver string into (major, minor, patch, pre-release)."""
    m = _SEMVER_RE.match(version.strip().lstrip("v"))
    if not m:
        return (0, 0, 0, "")
    return (
        int(m.group("major")),
        int(m.group("minor")),
        int(m.group("patch")),
        m.group("pre") or "",
    )


def _semver_cmp(a: str, b: str) -> int:
    """Compare two semver strings. Returns -1|0|1."""
    pa, pb = _parse_semver(a), _parse_semver(b)
    # Numeric part comparison
    for x, y in zip(pa[:3], pb[:3], strict=False):
        if x < y:
            return -1
        if x > y:
            return 1
    # Pre-release: presence means *less than* release (1.0.0-alpha < 1.0.0)
    if pa[3] and not pb[3]:
        return -1
    if not pa[3] and pb[3]:
        return 1
    if pa[3] < pb[3]:
        return -1
    if pa[3] > pb[3]:
        return 1
    return 0


def check_version_constraint(installed: str, constraint: str) -> bool:
    """Check *installed* version against a *constraint* like ``>=1.2.0``.

    Supported operators: ``>=``, ``>``, ``<=``, ``<``, ``==``, ``!=``, ``~=``
    (compatible release). An empty constraint always matches.
    """
    if not constraint:
        return True
    constraint = constraint.strip()
    for op in (">=", "<=", "!=", "==", "~=", ">", "<"):
        if constraint.startswith(op):
            ver = constraint[len(op) :].strip()
            cmp = _semver_cmp(installed, ver)
            if op == ">=":
                return cmp >= 0
            if op == ">":
                return cmp > 0
            if op == "<=":
                return cmp <= 0
            if op == "<":
                return cmp < 0
            if op == "==":
                return cmp == 0
            if op == "!=":
                return cmp != 0
            if op == "~=":
                # Compatible release: >=ver, <next major
                if cmp < 0:
                    return False
                pm = _parse_semver(ver)
                return _parse_semver(installed)[:1] == pm[:1]
            break
    # Bare version ⟹ exact match
    return _semver_cmp(installed, constraint) == 0


class CollectionManager:
    """Manages installation and lifecycle of workflow collections.

    Storage layout::

        ~/.ofx/collections/
            installed.json          # registry of installed collections
            <name>/                 # cloned collection directory
                *.yaml              # workflows
    """

    def __init__(self, base_dir: Path | None = None):
        from ofx.settings import BASE_DATA_DIR, ensure_dir

        self.base_dir = ensure_dir(base_dir or BASE_DATA_DIR / "collections")
        self.installed_file = self.base_dir / "installed.json"
        self._installed: dict[str, InstalledCollection] = self._load_installed()
        self._installing: set[str] = set()  # circular-dep guard

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_installed(self) -> dict[str, InstalledCollection]:
        if not self.installed_file.exists():
            return {}
        try:
            raw = json.loads(self.installed_file.read_text())
            return {k: InstalledCollection.model_validate(v) for k, v in raw.items()}
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(
                "Failed to load installed collections from %s: %s",
                self.installed_file,
                exc,
            )
            return {}

    def _save_installed(self) -> None:
        data = {k: v.model_dump() for k, v in self._installed.items()}
        self.installed_file.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # Add / Install
    # ------------------------------------------------------------------

    def add(
        self,
        name_or_url: str,
        *,
        alias: str = "",
        ref: str = "",
        install_deps: bool = True,
    ) -> InstalledCollection:
        """Install a collection from a git URL or local path.

        Args:
            name_or_url: Full git URL or local path.
            alias: Override the directory/display name.
            ref: Git tag or branch to pin (default: repo default branch).
            install_deps: Recursively install dependencies from collection.yaml.

        Returns:
            The ``InstalledCollection`` metadata.

        Raises:
            ValueError: If the collection is already installed.
            RuntimeError: If cloning fails.
        """
        source = name_or_url.strip()
        inferred_name = alias or Path(source).stem.removesuffix(".git")

        # Circular dependency guard
        if inferred_name in self._installing:
            logger.warning(
                "Circular dependency detected: '%s' is already being installed, skipping.",
                inferred_name,
            )
            existing = self._installed.get(inferred_name)
            if existing:
                return existing
            return InstalledCollection(name=inferred_name, source=source)

        if inferred_name in self._installed:
            raise ValueError(f"Collection '{inferred_name}' is already installed.")

        target = self.base_dir / inferred_name
        if target.exists():
            raise ValueError(
                f"Directory '{target}' already exists. Choose a different --name."
            )

        logger.info("Cloning %s …", source)
        clone_opts = ["--depth=1"]
        if ref:
            clone_opts.append(f"--branch={ref}")

        # Inject token into HTTPS URLs for private repo access
        clone_url = self._authenticated_url(source)

        try:
            git.Repo.clone_from(clone_url, str(target), multi_options=clone_opts)
        except GitCommandError as exc:
            raise RuntimeError(f"Failed to clone '{source}': {exc}") from exc

        # Validate cloned directory structure
        self._validate_collection_dir(target)

        self._installing.add(inferred_name)
        try:
            entry = InstalledCollection(
                name=inferred_name,
                source=source,
                pinned_ref=ref or self._current_ref(target),
                path=str(target),
                installed_at=datetime.now(UTC).isoformat(),
            )
            self._installed[inferred_name] = entry
            self._save_installed()
            logger.info("Installed collection '%s'", inferred_name)

            if install_deps:
                self._install_dependencies(target)

            return entry
        finally:
            self._installing.discard(inferred_name)

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove(self, name: str) -> bool:
        """Remove an installed collection by name."""
        entry = self._installed.get(name)
        if not entry:
            return False
        path = Path(entry.path)
        if path.exists():
            shutil.rmtree(path)
        del self._installed[name]
        self._save_installed()
        logger.info("Removed collection '%s'", name)
        return True

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, name: str = "") -> list[str]:
        """Pull latest changes for one or all collections.

        Returns list of collection names that were updated.
        """
        targets = {name: self._installed[name]} if name else dict(self._installed)
        updated: list[str] = []

        for coll_name, entry in targets.items():
            path = Path(entry.path)
            if not (path / ".git").exists():
                logger.warning("'%s' is not a git repo, skipping update.", coll_name)
                continue
            try:
                repo = git.Repo(path)
                if not repo.remotes:
                    logger.warning("'%s' has no remote, skipping.", coll_name)
                    continue
                repo.remotes.origin.pull()
                entry.pinned_ref = self._current_ref(path)
                updated.append(coll_name)
                logger.info("Updated '%s'", coll_name)
            except GitCommandError as exc:
                logger.error("Failed to update '%s': %s", coll_name, exc)
            except Exception as exc:
                logger.error("Unexpected error updating '%s': %s", coll_name, exc)

        if updated:
            self._save_installed()
        return updated

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_installed(self) -> dict[str, InstalledCollection]:
        """Return all installed collections."""
        return dict(self._installed)

    def get(self, name: str) -> InstalledCollection | None:
        """Get metadata for a single installed collection."""
        return self._installed.get(name)

    def info(self, name: str) -> InstalledCollection | None:
        """Get metadata for an installed collection."""
        return self._installed.get(name)

    def collection_workflow_dirs(self) -> list[Path]:
        """Return paths of all installed collections for workflow search."""
        return [Path(e.path) for e in self._installed.values() if Path(e.path).is_dir()]

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate_from_assets(self, assets_file: Path) -> int:
        """Import entries from the legacy assets.json into the collection registry.

        Returns the number of migrated collections.
        """
        if not assets_file.exists():
            return 0
        try:
            raw = json.loads(assets_file.read_text())
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning(
                "Failed to parse legacy assets file %s: %s", assets_file, exc
            )
            return 0

        count = 0
        for name, details in raw.items():
            if name in self._installed:
                continue
            old_path = Path(details.get("path", ""))
            if not old_path.exists():
                continue

            # Move into collections dir if stored elsewhere
            dest = self.base_dir / name
            if old_path != dest:
                if dest.exists():
                    continue
                shutil.copytree(old_path, dest)

            entry = InstalledCollection(
                name=name,
                source=details.get("url", ""),
                pinned_ref=self._current_ref(dest),
                path=str(dest),
            )
            self._installed[name] = entry
            count += 1

        if count:
            self._save_installed()
            logger.info("Migrated %d legacy asset(s) into collections.", count)
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_collection_dir(target: Path) -> None:
        """Warn if a cloned directory has no collection.yaml or workflow files."""
        if (target / "collection.yaml").exists():
            return
        if (target / "collection.yml").exists():
            return
        yaml_files = list(target.glob("*.yml")) + list(target.glob("*.yaml"))
        if yaml_files:
            return
        logger.warning(
            "Collection directory '%s' contains no collection.yaml or workflow files.",
            target,
        )

    def _install_dependencies(self, target: Path) -> None:
        """Read collection.yaml and recursively install listed dependencies."""
        manifest_path = target / "collection.yaml"
        if not manifest_path.exists():
            manifest_path = target / "collection.yml"
        if not manifest_path.exists():
            return
        try:
            import yaml

            manifest = yaml.safe_load(manifest_path.read_text()) or {}
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", manifest_path, exc)
            return

        deps = manifest.get("dependencies")
        if not deps or not isinstance(deps, list):
            return

        for dep in deps:
            dep_name = str(dep).strip()
            if not dep_name:
                continue
            if dep_name in self._installed:
                logger.debug("Dependency '%s' already installed, skipping.", dep_name)
                continue
            try:
                logger.info("Installing dependency '%s' …", dep_name)
                self.add(dep_name, install_deps=True)
            except (ValueError, RuntimeError) as exc:
                logger.warning(
                    "Failed to install dependency '%s': %s", dep_name, exc
                )

    @staticmethod
    def _current_ref(repo_path: Path) -> str:
        """Return the current HEAD short-ref of a git repo."""
        try:
            repo = git.Repo(repo_path)
            return str(repo.head.commit)[:12]
        except (git.InvalidGitRepositoryError, git.GitCommandError, ValueError) as e:
            logger.debug("Failed to get git ref for %s: %s", repo_path, e)
            return ""

    @staticmethod
    def _authenticated_url(source: str) -> str:
        """Inject a GitHub token into HTTPS clone URLs for private repo access.

        If no token is available or the URL is not an HTTPS GitHub URL,
        the original URL is returned unchanged.
        """
        from ofx.settings import get_github_token

        token = get_github_token()
        if not token:
            return source
        # Only inject into HTTPS GitHub URLs
        if source.startswith("https://github.com/"):
            return source.replace(
                "https://github.com/",
                f"https://x-access-token:{token}@github.com/",
                1,
            )
        return source
