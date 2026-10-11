"""Loading user-defined functions (UDFs) for OFX modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.modules.base import ModuleSpec
from ofx.utils.module_loader import load_module_from_file

DEFAULT_UDF_FUNCTION = "run"


def split_udf_spec(spec: str) -> tuple[Path, str]:
    """Split a ``<path>.py[::<function>]`` spec into a path and function name."""
    if "::" in spec:
        path_part, function = spec.rsplit("::", 1)
    else:
        path_part, function = spec, DEFAULT_UDF_FUNCTION
    path = Path(path_part)
    if not path.suffix == ".py":
        raise ValueError(
            f"Invalid module spec '{spec}': expected '<path>.py[::<function>]'"
        )
    return path, function


def resolve_udf_path(spec: str, workflow_dir: Path | None) -> Path:
    """Resolve a UDF file path against ``workflow_dir`` first, then the cwd."""
    path, _function = split_udf_spec(spec)
    if path.is_absolute():
        return path
    if workflow_dir is not None:
        candidate = workflow_dir / path
        if candidate.exists():
            return candidate
    return Path.cwd() / path


def load_module_file(
    path: Path, function: str, *, name: str | None = None
) -> ModuleSpec:
    """Load a Python file and return a UDF :class:`ModuleSpec`.

    Used for workflow-local named modules (``local.<name>``) and cached
    remote modules; performs the same file/function checks as
    :func:`load_udf_spec` but takes a concrete path instead of a spec.
    """
    resolved = path
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Module file not found: '{path}' (resolved to {resolved})"
        )
    module = load_module_from_file(resolved, "ofx.modules.udf")
    if module is None:
        raise ImportError(f"Failed to load module file: {resolved}")
    callable_obj: Any = getattr(module, function, None)
    if callable_obj is None:
        raise AttributeError(
            f"Function '{function}' not found in module file '{resolved}'"
        )
    if not callable(callable_obj):
        raise TypeError(f"'{function}' in module file '{resolved}' is not callable")
    return ModuleSpec(
        kind="udf",
        name=name or str(resolved),
        callable=callable_obj,
        file=resolved,
        function=function,
    )


def load_udf_spec(spec: str, workflow_dir: Path | None) -> ModuleSpec:
    """Load a UDF from ``<path>.py[::<function>]`` into a :class:`ModuleSpec`."""
    path_part, function = split_udf_spec(spec)
    resolved = resolve_udf_path(spec, workflow_dir)
    return load_module_file(resolved, function, name=spec)


__all__ = [
    "DEFAULT_UDF_FUNCTION",
    "load_module_file",
    "load_udf_spec",
    "resolve_udf_path",
    "split_udf_spec",
]
