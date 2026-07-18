"""Shared YAML config file helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("ofx")

def load_yaml_dict(path: Path, *, warn_prefix: str) -> dict[str, Any]:
    """Load a YAML mapping from file, returning an empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        logger.warning("%s from %s: %s", warn_prefix, path, exc)
        return {}

def save_yaml_dict(path: Path, data: dict[str, Any]) -> None:
    """Save a mapping to YAML with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
