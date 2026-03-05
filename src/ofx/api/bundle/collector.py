"""Collect .py files for requested ofx.api submodules into an archive-ready dict."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from .analyzer import KNOWN_API_MODULES, BundleError  # noqa: F401

__all__ = ["CollectionError", "collect_modules"]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CollectionError(BundleError):
    """Raised when a requested module's source files cannot be located."""

    def __init__(self, message: str, *, module_name: str | None = None) -> None:
        self.module_name = module_name
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_STUB_INIT = b"# ofx bundle stub\n"


def _resolve_api_root() -> Path:
    """Return the filesystem path of the ``ofx/api/`` package directory."""
    spec = importlib.util.find_spec("ofx.api")
    if spec is None or spec.origin is None:
        raise CollectionError(
            "Cannot locate ofx.api package – ensure ofx is installed in the current environment."
        )
    return Path(spec.origin).parent  # .../site-packages/ofx/api


def _pkg_files(module_name: str, api_root: Path) -> dict[str, bytes]:
    """Return ``{archive_path: bytes}`` for a single ``ofx.api`` submodule.

    The archive path is relative to the virtual ``site-packages/`` root so
    that extracting the archive adds importable packages directly.
    """
    site_packages = api_root.parent.parent  # .../site-packages

    pkg_dir = api_root / module_name
    if pkg_dir.is_dir():
        result: dict[str, bytes] = {}
        for py in sorted(pkg_dir.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            arc = py.relative_to(site_packages)
            result[arc.as_posix()] = py.read_bytes()
        return result

    flat = api_root / f"{module_name}.py"
    if flat.is_file():
        arc = flat.relative_to(site_packages)
        return {arc.as_posix(): flat.read_bytes()}

    raise CollectionError(
        f"No source file found for ofx.api.{module_name}",
        module_name=module_name,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_modules(module_names: set[str]) -> dict[str, bytes]:
    """Return ``{archive_path: bytes}`` for all requested ``ofx.api`` modules.

    Includes minimal ``ofx/api/__init__.py`` stubs so
    the extracted archive is a self-contained importable tree.

    Args:
        module_names: Names from :data:`~ofx.api.bundle.analyzer.KNOWN_API_MODULES`
            to collect.

    Returns:
        Mapping from archive-relative POSIX paths to raw file bytes.

    Raises:
        CollectionError: If any module's source files cannot be found.
    """
    api_root = _resolve_api_root()

    files: dict[str, bytes] = {
        "ofx/__init__.py": _STUB_INIT,
        "ofx/api/__init__.py": _STUB_INIT,
    }

    # Always include _compat.py — provides stdlib-only shims for
    # ofx.settings, ofx.exceptions, and ofx.utils.module_loader so
    # bundled API modules work on remote hosts without the full ofx package.
    compat_file = api_root / "_compat.py"
    if compat_file.is_file():
        site_packages = api_root.parent.parent
        arc = compat_file.relative_to(site_packages)
        files[arc.as_posix()] = compat_file.read_bytes()

    for name in sorted(module_names):
        files.update(_pkg_files(name, api_root))

    return files
