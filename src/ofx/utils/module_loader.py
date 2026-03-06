"""Helpers for loading plugin-style modules from the filesystem."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def module_name_for_path(prefix: str, path: Path) -> str:
    """Build a stable, unique module name for a file path."""
    digest = hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()[:10]
    return f"{prefix}.{path.stem}_{digest}"


def load_module_from_file(path: Path, module_prefix: str) -> ModuleType | None:
    """Load a module from a file path under a unique module namespace."""
    module_name = module_name_for_path(module_prefix, path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def iter_subclasses(module: ModuleType, base_class: type) -> list[type]:
    """Return subclasses of base_class defined in the given module."""
    subclasses: list[type] = []
    for attr in module.__dict__.values():
        if (
            isinstance(attr, type)
            and issubclass(attr, base_class)
            and attr is not base_class
        ):
            subclasses.append(attr)
    return subclasses
