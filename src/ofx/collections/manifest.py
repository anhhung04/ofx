"""Pydantic models for collection install metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class InstalledCollection(BaseModel):
    """Metadata for an installed collection stored in installed.json."""

    name: str
    version: str = "0.0.0"
    source: str = Field(default="", description="Git URL or shorthand used to install")
    pinned_ref: str = Field(default="", description="Git tag/branch pinned at install")
    path: str = Field(default="", description="Absolute path to installed directory")
    installed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    description: str = ""
    author: str = ""
    tags: list[str] = Field(default_factory=list)



