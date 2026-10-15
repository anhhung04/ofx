"""AST-based detection of ofx.lib.* imports used in a Python script."""

from __future__ import annotations

import ast
import importlib.util
import warnings
from pathlib import Path

__all__ = [
    "KNOWN_API_MODULES",
    "BundleError",
    "AnalysisError",
    "detect_ofx_imports",
    "detect_ofx_import_paths",
]

KNOWN_API_MODULES: frozenset[str] = frozenset(
    {
        "ad",
        "c2",
        "creds",
        "data",
        "dns",
        "evasion",
        "exfil",
        "exploitation",
        "file",
        "http",
        "httpserver",
        "lateral",
        "loot",
        "network",
        "oob",
        "opsec",
        "packers",
        "payloads",
        "persistence",
        "post",
        "privesc",
        "recon",
        "search",
        "service",
        "strings",
        "utils",
        "bundle",
    }
)

class BundleError(Exception):
    """Base exception for all bundle operations."""

class AnalysisError(BundleError):
    """Raised when AST parsing or module analysis fails."""

    def __init__(self, message: str, *, source: str | None = None) -> None:
        self.source = source
        super().__init__(message)

def _find_api_root() -> Path | None:
    """Return the filesystem path of the ``ofx/lib/`` package directory.

    Returns ``None`` when ``ofx.lib`` is not importable in the current
    environment (e.g. analysis running before the package is installed).
    """
    spec = importlib.util.find_spec("ofx.lib")
    if spec is None or spec.origin is None:
        return None
    return Path(spec.origin).parent

def _paths_from_node(node: ast.AST) -> set[str]:
    """Return ``ofx.lib`` dotted paths (relative to ``ofx.lib``) in one node.

    Examples::

        import ofx.lib.opsec.proxy                     -> {"opsec.proxy"}
        from ofx.lib import opsec, c2                  -> {"opsec", "c2"}
        from ofx.lib.opsec import clean_history_commands
                                                       -> {"opsec"}
        from ofx.lib.opsec.cleanup import clean_history_commands
                                                       -> {"opsec.cleanup"}
    """
    found: set[str] = set()

    if isinstance(node, ast.Import):
        for alias in node.names:
            prefix = "ofx.lib."
            if alias.name.startswith(prefix):
                rest = alias.name[len(prefix) :]
                if rest:
                    found.add(rest)

    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""

        if module == "ofx.lib":
            for alias in node.names:
                found.add(alias.name)

        elif module.startswith("ofx.lib."):
            rest = module[len("ofx.lib.") :]
            if rest:
                found.add(rest)

    return found

def _relative_paths(node: ast.ImportFrom, module_path: str) -> set[str]:
    """Resolve an ``ImportFrom`` with a relative level against *module_path*.

    *module_path* is the dotted path of the importing file relative to
    ``ofx.lib`` (e.g. ``"post.base"`` for ``ofx/lib/post/base.py``).
    ``from .X import y`` inside it resolves to ``post.X``.
    """
    segments = module_path.split(".")
    base = segments[: len(segments) - node.level] if node.level <= len(segments) else []
    if node.module:
        return {".".join(base + [node.module])}
    return {
        ".".join(base + [alias.name])
        for alias in node.names
        if alias.name != "*"
    }

def _validate_api_paths(paths: set[str], api_root: Path | None) -> set[str]:
    """Keep only paths whose every segment resolves under ``ofx/lib/``."""
    if not paths:
        return set()
    valid: set[str] = set()
    for path in sorted(paths):
        if api_root is None:
            # Fallback when ofx.lib is not installed: keep known top-levels.
            top = path.split(".")[0]
            if top in KNOWN_API_MODULES:
                valid.add(top)
            continue
        node = api_root
        ok = True
        for segment in path.split("."):
            node = node / segment
            if not (node.is_dir() or node.with_suffix(".py").is_file()):
                ok = False
                break
        if ok:
            valid.add(path)
    return valid

def _scan_import_paths(
    source: str,
    *,
    source_name: str = "<module>",
    module_path: str | None = None,
) -> set[str]:
    """Return raw (unvalidated) ``ofx.lib`` paths referenced in *source*.

    Used by the collector to compute the transitive closure of bundled
    modules.  When *module_path* is given, relative ``from .X import ...``
    statements inside the source are resolved against it so sibling modules
    of a partially packed package are discovered too.  Unparseable sources
    yield no paths (best-effort scan).
    """
    try:
        tree = ast.parse(source, filename=source_name)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        found |= _paths_from_node(node)
        if module_path is not None and isinstance(node, ast.ImportFrom) and node.level:
            found |= _relative_paths(node, module_path)
    return found

def detect_ofx_import_paths(
    script: str,
    *,
    extra_modules: list[str] | None = None,
    source_name: str = "<script>",
) -> set[str]:
    """Parse *script* and return the ``ofx.lib`` dotted paths it uses.

    Paths are relative to ``ofx.lib``::

        import ofx.lib.opsec.proxy               -> {"opsec.proxy"}
        from ofx.lib import opsec, c2            -> {"opsec", "c2"}
        from ofx.lib.opsec import clean_history_commands
                                                 -> {"opsec"}
        from ofx.lib.opsec.cleanup import clean_history_commands
                                                 -> {"opsec.cleanup"}
        import ofx.lib.recon                     -> {"recon"}

    Every segment is validated against the real package tree under
    ``ofx/lib/``; unknown paths are silently dropped (they may be
    user-defined modules that happen to share an ``ofx.lib`` prefix).

    Args:
        script: Python source code to analyse.
        extra_modules: Additional module names or dotted paths to always
            include, regardless of what the AST finds.  Top-level names
            (e.g. ``"recon"``) pack the whole package; dotted paths
            (e.g. ``"recon.targets"`` or ``"ofx.lib.recon.targets"``) are
            honoured.  Invalid entries emit a warning.
        source_name: Label used in error messages (e.g. a filename).

    Returns:
        Set of dotted paths relative to ``ofx.lib``.

    Raises:
        AnalysisError: If *script* cannot be parsed as valid Python.
    """
    try:
        tree = ast.parse(script, filename=source_name)
    except SyntaxError as exc:
        raise AnalysisError(
            f"Cannot parse script {source_name!r}: {exc}",
            source=source_name,
        ) from exc

    found: set[str] = set()
    for node in ast.walk(tree):
        found |= _paths_from_node(node)

    if extra_modules:
        for name in extra_modules:
            normalized = name[8:] if name.startswith("ofx.lib.") else name
            if normalized:
                found.add(normalized)
            else:
                warnings.warn(
                    f"extra_modules: {name!r} is not a known ofx.lib module "
                    f"or path and will be ignored.",
                    stacklevel=2,
                )

    validated = _validate_api_paths(found, _find_api_root())

    if extra_modules:
        for name in extra_modules:
            normalized = name[8:] if name.startswith("ofx.lib.") else name
            if normalized and normalized not in validated:
                warnings.warn(
                    f"extra_modules: {name!r} is not a known ofx.lib module "
                    f"or path and will be ignored.",
                    stacklevel=2,
                )

    return validated

def detect_ofx_imports(
    script: str,
    *,
    extra_modules: list[str] | None = None,
    source_name: str = "<script>",
) -> set[str]:
    """Parse *script* and return the set of ``ofx.lib`` submodule names used.

    Thin wrapper over :func:`detect_ofx_import_paths` returning the
    top-level segments of each resolved dotted path.  Covers all four import
    patterns::

        import ofx.lib.opsec
        from ofx.lib import opsec, c2
        from ofx.lib.opsec import clean_history_commands
        from ofx.lib.opsec.cleanup import clean_history_commands

    All resolved names are validated against :data:`KNOWN_API_MODULES`.
    Unknown names are silently dropped (they may be user-defined modules
    that happen to share a name with an OFX module).

    Args:
        script: Python source code to analyse.
        extra_modules: Additional module names to always include,
            regardless of what the AST finds.  Invalid names emit a warning.
        source_name: Label used in error messages (e.g. a filename).

    Returns:
        Set of ``ofx.lib`` top-level module names, e.g. ``{"opsec", "c2"}``.

    Raises:
        AnalysisError: If *script* cannot be parsed as valid Python.
    """
    paths = detect_ofx_import_paths(
        script, extra_modules=extra_modules, source_name=source_name
    )
    return {
        top
        for top in (path.split(".")[0] for path in paths)
        if top in KNOWN_API_MODULES
    }
