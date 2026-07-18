"""Helpers for normalizing targets used in export paths."""

from __future__ import annotations

import re

_UNSAFE_TARGET_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")
_MULTIPLE_UNDERSCORES_RE = re.compile(r"_+")

def sanitize_target_slug(target: str) -> str:
    """Return a filesystem-safe slug for a target string."""
    if not target:
        return ""

    slug = target
    if target.startswith(("http://", "https://")):
        slug = target.split("://", 1)[1].split("/", 1)[0]

    slug = _UNSAFE_TARGET_CHARS_RE.sub("_", slug)
    slug = _MULTIPLE_UNDERSCORES_RE.sub("_", slug).strip("_")
    return slug[:120]

__all__ = ["sanitize_target_slug"]
