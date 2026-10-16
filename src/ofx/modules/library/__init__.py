"""Library modules — declared wrappers for ofx.lib functions.

Each module in this package wraps one ofx.lib function with a declared
name, description, args_schema, and run(ctx) entry point. They are
registered alongside builtins and tools so users see one unified module
catalog — no api-vs-module ambiguity.

Generated from api function signatures; hand-tune as needed.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from ofx.modules.base import ModuleSpec


def _iter_library_modules():
    """Import every module in this package and yield it."""
    for _importer, modname, _ispkg in pkgutil.iter_modules(__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"ofx.modules.library.{modname}")
        if hasattr(mod, "name") and hasattr(mod, "run"):
            yield mod


def build_library_specs() -> dict[str, ModuleSpec]:
    """Build ModuleSpec entries for all library modules."""
    specs: dict[str, ModuleSpec] = {}
    for mod in _iter_library_modules():
        spec = ModuleSpec(
            kind="lib",
            name=mod.name,
            description=mod.description,
            args_schema=mod.args_schema,
            callable=mod.run,
        )
        specs[spec.name] = spec
    return specs


__all__ = ["build_library_specs"]
