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

from ofx.collections.manifest import CollectionManifest, InstalledCollection
from ofx.settings import settings

logger = logging.getLogger(settings.app_branding)

DEFAULT_COLLECTION_ORG = "https://github.com/ofx-workflows"
MANIFEST_FILENAME = "collection.yaml"


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
                collection.yaml     # manifest
                *.yaml              # workflows
    """

    def __init__(self, base_dir: Path | None = None):
        from ofx.settings import BASE_DATA_DIR, ensure_dir

        self.base_dir = ensure_dir(base_dir or BASE_DATA_DIR / "collections")
        self.installed_file = self.base_dir / "installed.json"
        self._installed: dict[str, InstalledCollection] = self._load_installed()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_installed(self) -> dict[str, InstalledCollection]:
        if not self.installed_file.exists():
            return {}
        try:
            raw = json.loads(self.installed_file.read_text())
            return {k: InstalledCollection.model_validate(v) for k, v in raw.items()}
        except (json.JSONDecodeError, Exception):
            return {}

    def _save_installed(self) -> None:
        data = {k: v.model_dump() for k, v in self._installed.items()}
        self.installed_file.write_text(json.dumps(data, indent=2))

    # ------------------------------------------------------------------
    # Resolve source URL
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_source(name_or_url: str) -> str:
        """Resolve a collection name or URL to a full git URL.

        - Full URL  → pass through
        - org/repo  → https://github.com/org/repo
        - bare name → https://github.com/ofx-workflows/<name>
        """
        if name_or_url.startswith(("https://", "http://", "git@", "ssh://")):
            return name_or_url
        if "/" in name_or_url:
            return f"https://github.com/{name_or_url}"
        return f"{DEFAULT_COLLECTION_ORG}/{name_or_url}"

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
        """Install a collection from a git URL or shorthand name.

        Args:
            name_or_url: Full git URL, ``org/repo``, or bare collection name
                (resolved to ``ofx-workflows`` org).
            alias: Override the directory/display name.
            ref: Git tag or branch to pin (default: repo default branch).
            install_deps: Recursively install declared dependencies.

        Returns:
            The ``InstalledCollection`` metadata.

        Raises:
            ValueError: If the collection is already installed.
            RuntimeError: If cloning fails.
        """
        source = self.resolve_source(name_or_url)
        inferred_name = alias or Path(source).stem.removesuffix(".git")

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

        # Read manifest (or synthesize one)
        manifest = CollectionManifest.from_directory(target)

        # --- min_ofx_version gate ---
        self._check_min_ofx_version(manifest, inferred_name)

        entry = InstalledCollection(
            name=inferred_name,
            version=manifest.version,
            source=source,
            pinned_ref=ref or self._current_ref(target),
            path=str(target),
            installed_at=datetime.now(UTC).isoformat(),
            description=manifest.description,
            author=manifest.author,
            tags=manifest.tags,
        )
        self._installed[inferred_name] = entry
        self._save_installed()
        logger.info("Installed collection '%s' v%s", inferred_name, manifest.version)

        # --- recursive dependency resolution ---
        if install_deps and manifest.dependencies:
            self._install_dependencies(manifest.dependencies)

        return entry
        return entry

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
                # Refresh manifest
                manifest = CollectionManifest.from_directory(path)
                entry.version = manifest.version
                entry.pinned_ref = self._current_ref(path)
                entry.description = manifest.description
                entry.author = manifest.author
                entry.tags = manifest.tags
                updated.append(coll_name)
                logger.info("Updated '%s' → v%s", coll_name, manifest.version)
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

    def info(self, name: str) -> CollectionManifest | None:
        """Read the full manifest of an installed collection."""
        entry = self._installed.get(name)
        if not entry:
            return None
        path = Path(entry.path)
        if not path.exists():
            return None
        return CollectionManifest.from_directory(path)

    def collection_workflow_dirs(self) -> list[Path]:
        """Return paths of all installed collections for workflow search."""
        return [
            Path(e.path) for e in self._installed.values() if Path(e.path).is_dir()
        ]

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
        except (json.JSONDecodeError, Exception):
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

            manifest = CollectionManifest.from_directory(dest)
            entry = InstalledCollection(
                name=name,
                version=manifest.version,
                source=details.get("url", ""),
                pinned_ref=self._current_ref(dest),
                path=str(dest),
                description=manifest.description,
                author=manifest.author,
                tags=manifest.tags,
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
    def _current_ref(repo_path: Path) -> str:
        """Return the current HEAD short-ref of a git repo."""
        try:
            repo = git.Repo(repo_path)
            return str(repo.head.commit)[:12]
        except Exception:
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

    @staticmethod
    def _check_min_ofx_version(manifest: CollectionManifest, name: str) -> None:
        """Warn (non-fatal) if OFX version is below the collection requirement."""
        if not manifest.min_ofx_version:
            return
        try:
            from ofx import __version__ as ofx_version
        except ImportError:
            return
        if not check_version_constraint(ofx_version, f">={manifest.min_ofx_version}"):
            logger.warning(
                "Collection '%s' requires OFX >= %s (you have %s). "
                "Some features may not work.",
                name,
                manifest.min_ofx_version,
                ofx_version,
            )

    def _install_dependencies(self, deps: list) -> None:
        """Recursively install collection dependencies.

        Already-installed collections are skipped.  Version constraints are
        checked against what is installed; a warning is logged on mismatch.
        """
        from ofx.collections.manifest import CollectionDependency

        for dep in deps:
            if not isinstance(dep, CollectionDependency):
                dep = CollectionDependency.model_validate(dep)

            existing = self._installed.get(dep.name)
            if existing:
                if dep.version and not check_version_constraint(
                    existing.version, dep.version
                ):
                    logger.warning(
                        "Dependency '%s' installed as v%s but constraint is %s",
                        dep.name,
                        existing.version,
                        dep.version,
                    )
                continue

            # Install the dependency
            source = dep.source or dep.name  # bare name → ofx-workflows org
            try:
                logger.info("Installing dependency '%s' …", dep.name)
                self.add(source, alias=dep.name, install_deps=True)
            except (ValueError, RuntimeError) as exc:
                logger.warning(
                    "Could not install dependency '%s': %s", dep.name, exc
                )
