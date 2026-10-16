"""Collect .py files for requested ofx.lib submodules into an archive-ready dict."""

from __future__ import annotations

import ast
from pathlib import Path

from .analyzer import (
    BundleError,
    _find_api_root,
    _scan_import_paths,
    _validate_api_paths,
)

__all__ = ["CollectionError", "collect_modules", "collect_modules_granular"]

class CollectionError(BundleError):
    """Raised when a requested module's source files cannot be located."""

    def __init__(self, message: str, *, module_name: str | None = None) -> None:
        self.module_name = module_name
        super().__init__(message)

_STUB_INIT = b"# ofx bundle stub\n"

def _resolve_api_root() -> Path:
    """Return the filesystem path of the ``ofx/lib/`` package directory."""
    root = _find_api_root()
    if root is None:
        raise CollectionError(
            "Cannot locate ofx.lib package – ensure ofx is installed in the current environment."
        )
    return root

def _pkg_files(module_name: str, api_root: Path) -> dict[str, bytes]:
    """Return ``{archive_path: bytes}`` for a single ``ofx.lib`` submodule.

    The archive path is relative to the virtual ``site-packages/`` root so
    that extracting the archive adds importable packages directly.
    ``module_name`` may be dotted (e.g. ``"exploitation.shellcode"``).
    """
    site_packages = api_root.parent.parent
    rel = Path(*module_name.split("."))

    pkg_dir = api_root / rel
    if pkg_dir.is_dir():
        result: dict[str, bytes] = {}
        for py in sorted(pkg_dir.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            arc = py.relative_to(site_packages)
            result[arc.as_posix()] = py.read_bytes()
        return result

    flat = api_root.joinpath(*module_name.split(".")).with_suffix(".py")
    if flat.is_file():
        arc = flat.relative_to(site_packages)
        return {arc.as_posix(): flat.read_bytes()}

    raise CollectionError(
        f"No source file found for ofx.lib.{module_name}",
        module_name=module_name,
    )

def collect_modules(module_names: set[str]) -> dict[str, bytes]:
    """Return ``{archive_path: bytes}`` for all requested ``ofx.lib`` modules.

    Includes minimal ``ofx/lib/__init__.py`` stubs so
    the extracted archive is a self-contained importable tree.

    Args:
        module_names: Names from :data:`~ofx.lib.bundle.analyzer.KNOWN_API_MODULES`
            to collect.

    Returns:
        Mapping from archive-relative POSIX paths to raw file bytes.

    Raises:
        CollectionError: If any module's source files cannot be found.
    """
    api_root = _resolve_api_root()

    files: dict[str, bytes] = {
        "ofx/__init__.py": _STUB_INIT,
        "ofx/lib/__init__.py": _STUB_INIT,
    }

    compat_file = api_root / "_compat.py"
    if compat_file.is_file():
        site_packages = api_root.parent.parent
        arc = compat_file.relative_to(site_packages)
        files[arc.as_posix()] = compat_file.read_bytes()

    for name in sorted(module_names):
        files.update(_pkg_files(name, api_root))

    return files

def _is_all_assignment(stmt: ast.Assign) -> bool:
    """True for ``__all__ = ["a", "b", ...]`` (list/tuple of string literals)."""
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        return False
    if stmt.targets[0].id != "__all__":
        return False
    if not isinstance(stmt.value, (ast.List, ast.Tuple)):
        return False
    return all(
        isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        for elt in stmt.value.elts
    )

def _init_is_stub_safe(dotted: str, api_root: Path) -> bool:
    """True when a package's real ``__init__.py`` only re-exports.

    A lazy stub can only replace the real ``__init__`` when that module does
    nothing but a docstring, imports and an ``__all__`` assignment.  Anything
    else (locally defined functions/classes, module-level calls or state) is
    a side effect a stub would silently drop — such packages keep their real
    ``__init__`` and are packed whole.
    """
    init = api_root.joinpath(*dotted.split("."), "__init__.py")
    if not init.is_file():
        return False
    try:
        tree = ast.parse(init.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue  # docstring
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            continue  # re-export imports are fine
        if isinstance(stmt, ast.Assign) and _is_all_assignment(stmt):
            continue
        return False
    return True

def _module_mapping(
    dotted: str, api_root: Path
) -> tuple[dict[str, str], list[str]]:
    """Return ``(name -> submodule, __all__ names)`` for a stub-safe package.

    Parses the real ``__init__.py``:

    * ``from .X import a, b`` maps ``a`` and ``b`` to submodule ``X``;
    * ``from . import X, Y`` (and the self-relative form
      ``from ofx.lib.<self> import X``) maps ``X -> X``, ``Y -> Y``;
    * every direct submodule (module file or package dir) maps to itself so
      ``pkg.submodule`` attribute access works lazily too.

    Returns the mapping plus the preserved ``__all__`` names (the sorted
    mapping keys when the real module does not define ``__all__``).
    """
    init = api_root.joinpath(*dotted.split("."), "__init__.py")
    tree = ast.parse(init.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    all_names: list[str] | None = None
    self_abs = f"ofx.lib.{dotted}" if dotted else "ofx.lib"

    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom):
            if stmt.level == 1:
                if stmt.module:
                    sub = stmt.module
                    for alias in stmt.names:
                        if alias.name != "*":
                            mapping[alias.asname or alias.name] = sub
                else:
                    for alias in stmt.names:
                        mapping[alias.asname or alias.name] = alias.name
            elif stmt.level == 0 and stmt.module == self_abs:
                for alias in stmt.names:
                    mapping[alias.asname or alias.name] = alias.name
        elif isinstance(stmt, ast.Assign) and _is_all_assignment(stmt):
            all_names = [elt.value for elt in stmt.value.elts]

    for child in sorted(init.parent.iterdir()):
        name = child.name
        if name.startswith("_") or name == "__pycache__":
            continue
        if child.is_file() and child.suffix == ".py":
            mapping.setdefault(name[:-3], name[:-3])
        elif child.is_dir() and (child / "__init__.py").is_file():
            mapping.setdefault(name, name)
        elif child.is_dir() and any(child.rglob("*.py")):
            mapping.setdefault(name, name)  # namespace subpackage with content

    return mapping, all_names if all_names is not None else sorted(mapping)

_LAZY_INIT_TEMPLATE = '''\
"""Lazy {display} subpackage stub (ofx bundle, file-granular packing)."""

import importlib as _importlib

__all__ = {all_repr}

_SUBMODULES = {mapping_repr}

def __getattr__(name):
    submodule = _SUBMODULES.get(name)
    if submodule is None:
        raise AttributeError("module {{0!r}} has no attribute {{1!r}}".format(__name__, name))
    module = _importlib.import_module(".".join((__name__, submodule)))
    if hasattr(module, name):
        return getattr(module, name)
    if name == submodule:
        return module
    raise AttributeError("module {{0!r}} has no attribute {{1!r}}".format(__name__, name))

def __dir__():
    return sorted(_SUBMODULES)
'''

def _make_lazy_stub(dotted: str, api_root: Path) -> bytes:
    """Build lazy ``__init__.py`` stub bytes for a stub-safe package.

    The stub maps every exported name and direct submodule to its submodule
    and resolves attributes lazily through a PEP 562 ``__getattr__``, so no
    sibling module is imported (or packed) until actually used.
    """
    mapping, all_names = _module_mapping(dotted, api_root)
    return _LAZY_INIT_TEMPLATE.format(
        display=dotted or "ofx.lib",
        all_repr=repr(all_names),
        mapping_repr=repr(mapping),
    ).encode("utf-8")

def collect_modules_granular(paths: set[str]) -> dict[str, bytes]:
    """Collect ``ofx.lib`` files with file-granular packing and lazy stubs.

    ``paths`` are dotted paths relative to ``ofx.lib``, as returned by
    :func:`~ofx.lib.bundle.analyzer.detect_ofx_import_paths`.  For each one:

    * module-file leaves are bundled alone;
    * every package directory on the path gets a lazy ``__init__.py`` stub
      (PEP 562 ``__getattr__``) unless its real ``__init__`` has side
      effects beyond re-exports — then the whole package directory is packed
      with the real ``__init__``;
    * depth-1 (bare) package paths keep the whole-package fallback;
    * the ``ofx/lib/__init__.py`` stub is always lazy-mapped.

    The transitive closure over ``ofx.lib`` imports (absolute and relative)
    inside every packed module is computed to a fixpoint, so dependencies of
    bundled files are included too.

    Returns:
        Mapping from archive-relative POSIX paths to raw file bytes.

    Raises:
        CollectionError: If any required module file cannot be found.
    """
    api_root = _resolve_api_root()
    site_packages = api_root.parent.parent

    def arc(path: Path) -> str:
        return path.relative_to(site_packages).as_posix()

    files: dict[str, bytes] = {"ofx/__init__.py": _STUB_INIT}
    compat_file = api_root / "_compat.py"
    if compat_file.is_file():
        files[arc(compat_file)] = compat_file.read_bytes()

    stubs: dict[str, bytes] = {
        arc(api_root / "__init__.py"): _make_lazy_stub("", api_root)
    }
    seen_paths: set[str] = set()
    scanned: set[str] = set()
    queued: list[str] = sorted(paths)

    def enqueue_imports(arc_name: str, data: bytes) -> None:
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError:
            return
        if arc_name.startswith("ofx/lib/") and arc_name.endswith(".py"):
            module_path = arc_name[len("ofx/lib/") : -3]
        else:
            module_path = None
        found = _scan_import_paths(source, source_name=arc_name, module_path=module_path)
        for path in sorted(_validate_api_paths(found, api_root)):
            if path not in seen_paths:
                queued.append(path)

    while queued:
        path = queued.pop(0)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        segments = path.split(".")
        node = api_root.joinpath(*segments)
        if not (node.exists() or node.with_suffix(".py").exists()):
            continue

        if node.is_dir():
            if len(segments) == 1 or not _init_is_stub_safe(path, api_root):
                packed = _pkg_files(path, api_root)
                for arc_name, data in packed.items():
                    if arc_name.endswith(".py") and arc_name not in scanned:
                        scanned.add(arc_name)
                        enqueue_imports(arc_name, data)
                    files[arc_name] = data
            else:
                stub_arc = arc(node / "__init__.py")
                stubs.setdefault(stub_arc, _make_lazy_stub(path, api_root))
        else:
            mod = node.with_suffix(".py")
            if mod.is_file():
                arc_name = arc(mod)
                if arc_name not in scanned:
                    scanned.add(arc_name)
                    enqueue_imports(arc_name, mod.read_bytes())
                files[arc_name] = mod.read_bytes()

        for depth in range(1, len(segments)):
            ancestor = ".".join(segments[:depth])
            if ancestor in seen_paths:
                continue
            anc_node = api_root.joinpath(*segments[:depth])
            if not anc_node.is_dir() or not (anc_node / "__init__.py").is_file():
                continue
            if _init_is_stub_safe(ancestor, api_root):
                stub_arc = arc(anc_node / "__init__.py")
                stubs.setdefault(stub_arc, _make_lazy_stub(ancestor, api_root))
            else:
                queued.append(ancestor)

    # Real __init__ files packed whole always win over scheduled stubs.
    for arc_name, stub in stubs.items():
        files.setdefault(arc_name, stub)
    return files
