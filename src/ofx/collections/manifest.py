"""Pydantic models for collection manifests and install metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class CollectionDependency(BaseModel):
    """A dependency on another collection."""

    name: str = Field(..., description="Collection name")
    version: str = Field(default="", description="Version constraint (e.g. '>=1.0.0')")
    source: str = Field(default="", description="Git URL override for this dependency")


class CollectionManifest(BaseModel):
    """Parsed collection.yaml from a collection repository."""

    name: str = Field(..., description="Collection name")
    version: str = Field(default="0.0.0", description="Semver version string")
    description: str = Field(default="", description="Human-readable description")
    author: str = Field(default="", description="Author or team name")
    license: str = Field(default="", description="License identifier")
    min_ofx_version: str = Field(default="", description="Minimum OFX version required")
    workflows: list[str] = Field(default_factory=list, description="Workflow files in this collection")
    tools: list[str] = Field(default_factory=list, description="Tool names this collection needs")
    dependencies: list[CollectionDependency] = Field(
        default_factory=list, description="Other collections this depends on"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for discoverability")

    @classmethod
    def from_yaml(cls, path: Path) -> CollectionManifest:
        """Load a manifest from a collection.yaml file."""
        import yaml

        data = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(data)

    @classmethod
    def from_directory(cls, path: Path) -> CollectionManifest:
        """Load manifest from a directory, falling back to a synthetic one.

        When no ``collection.yaml`` exists, a synthetic manifest is created
        from the directory name and any ``.yml``/``.yaml`` files found.
        Even when a manifest *does* exist, if its ``workflows`` list is
        empty the discovered YAML files are populated automatically.
        """
        manifest_path = path / "collection.yaml"
        if manifest_path.exists():
            manifest = cls.from_yaml(manifest_path)
        else:
            # Fallback: no manifest, synthesize from directory name
            manifest = cls(name=path.name)

        # Auto-discover workflow files when not explicitly listed
        if not manifest.workflows:
            manifest.workflows = cls._discover_workflows(path)
        return manifest

    @staticmethod
    def _discover_workflows(path: Path) -> list[str]:
        """Return relative names of all .yml/.yaml files in *path* (non-recursive)."""
        found: list[str] = []
        for ext in (".yml", ".yaml"):
            for f in sorted(path.glob(f"*{ext}")):
                if f.name == "collection.yaml":
                    continue
                found.append(f.name)
        return found


class InstalledCollection(BaseModel):
    """Metadata for an installed collection stored in installed.json."""

    name: str
    version: str = "0.0.0"
    source: str = Field(default="", description="Git URL or shorthand used to install")
    pinned_ref: str = Field(default="", description="Git tag/branch pinned at install")
    path: str = Field(default="", description="Absolute path to installed directory")
    installed_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    description: str = ""
    author: str = ""
    tags: list[str] = Field(default_factory=list)


class CollectionIndexEntry(BaseModel):
    """A single entry in the remote community index."""

    name: str
    description: str = ""
    source: str = ""
    latest: str = ""
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    private: bool = Field(default=False, description="Whether this collection is in a private repo")


class CollectionIndex(BaseModel):
    """The full remote index of available community collections."""

    collections: dict[str, CollectionIndexEntry] = Field(default_factory=dict)

    def search(self, query: str) -> list[CollectionIndexEntry]:
        """Search collections by name or tag (case-insensitive substring)."""
        q = query.lower()
        results: list[CollectionIndexEntry] = []
        for entry in self.collections.values():
            if (
                q in entry.name.lower()
                or q in entry.description.lower()
                or any(q in t.lower() for t in entry.tags)
            ):
                results.append(entry)
        return results
