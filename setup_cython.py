"""Cython compilation script for OFX.

Compiles all Python modules under src/ofx/ into C extensions (.so on Linux,
.pyd on Windows) for performance and source code protection.

Usage:
    python setup_cython.py build_ext --inplace
    # Or via Makefile:
    make compile

Incompatible files are detected via fast regex checks (match/case statements,
PEP 695 generics, Pydantic models, etc.) and excluded automatically.
A hash-based cache in build/.cython_cache.json skips re-checking unchanged
files on subsequent runs.
"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, find_packages, setup

SRC_DIR = Path("src")
PACKAGE_DIR = SRC_DIR / "ofx"
CACHE_FILE = Path("build") / ".cython_cache.json"

EXCLUDE_PATTERNS = {
    "__init__.py",  # package init — needed for discovery
    "_version.py",  # importlib.metadata at import time
    "conftest.py",  # pytest fixtures
}

EXCLUDE_DIRS = {
    "data",  # YAML workflows, static site assets
    "commands",  # Typer CLI — relies on signature introspection
    "models",  # Pydantic models — validators break under Cython
    "__pycache__",
}

# ── Regex patterns for Cython-incompatible syntax ────────────────
# Pydantic BaseModel subclasses (validators become cyfunction)
_PYDANTIC_MARKERS = re.compile(
    r"class\s+\w+\(.*(?:BaseModel|OFXBaseModel|BaseSettings).*\):",
    re.MULTILINE,
)

# @staticmethod + @lru_cache combo breaks under Cython
_STATIC_LRU_COMBO = re.compile(
    r"@staticmethod\s+@lru_cache|@lru_cache.*\s+@staticmethod",
    re.MULTILINE,
)

# match/case statements (Python 3.10+, unsupported by Cython)
_MATCH_CASE = re.compile(
    r"^\s*match\s+.+:\s*$",
    re.MULTILINE,
)

# PEP 695 generics: class Foo[T]: or def foo[T]( (Python 3.12+)
_PEP695_GENERIC = re.compile(
    r"(?:class|def)\s+\w+\[",
    re.MULTILINE,
)

# PEP 695 type aliases: type Foo = ...
_PEP695_TYPE_ALIAS = re.compile(
    r"^type\s+\w+\s*=",
    re.MULTILINE,
)

_INCOMPATIBLE_PATTERNS = [
    (_PYDANTIC_MARKERS, "pydantic model"),
    (_STATIC_LRU_COMBO, "staticmethod+lru_cache"),
    (_MATCH_CASE, "match/case statement"),
    (_PEP695_GENERIC, "PEP 695 generic"),
    (_PEP695_TYPE_ALIAS, "PEP 695 type alias"),
]


def _file_hash(path: Path) -> str:
    """Fast content hash for cache invalidation."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def _load_cache() -> dict:
    """Load the compatibility cache from disk."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache: dict) -> None:
    """Persist the compatibility cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _check_compatible(text: str) -> str | None:
    """Return skip reason if file has Cython-incompatible syntax, else None."""
    for pattern, reason in _INCOMPATIBLE_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def collect_extensions() -> tuple[list[Extension], list[str]]:
    """Walk src/ofx/ and create Extension objects for compilable .py files."""
    start = time.monotonic()
    cache = _load_cache()

    candidates = []
    for py_file in sorted(PACKAGE_DIR.rglob("*.py")):
        if py_file.name in EXCLUDE_PATTERNS:
            continue
        if any(part in EXCLUDE_DIRS for part in py_file.parts):
            continue
        candidates.append(py_file)

    extensions: list[Extension] = []
    skipped: list[str] = []
    cache_hits = 0
    new_cache: dict = {}

    for py_file in candidates:
        key = str(py_file)
        try:
            file_hash = _file_hash(py_file)
        except OSError:
            skipped.append(key)
            continue

        # Check cache — skip re-analysis if file unchanged
        cached = cache.get(key)
        if cached and cached.get("hash") == file_hash:
            cache_hits += 1
            if cached.get("ok"):
                rel = py_file.relative_to(SRC_DIR)
                module_name = str(rel.with_suffix("")).replace(os.sep, ".")
                extensions.append(Extension(module_name, [key]))
                new_cache[key] = cached
            else:
                skipped.append(key)
                new_cache[key] = cached
            continue

        # Fast regex check
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            skipped.append(key)
            new_cache[key] = {"hash": file_hash, "ok": False, "reason": "read error"}
            continue

        reason = _check_compatible(text)
        if reason:
            skipped.append(key)
            new_cache[key] = {"hash": file_hash, "ok": False, "reason": reason}
            continue

        # File passed all checks
        rel = py_file.relative_to(SRC_DIR)
        module_name = str(rel.with_suffix("")).replace(os.sep, ".")
        extensions.append(Extension(module_name, [key]))
        new_cache[key] = {"hash": file_hash, "ok": True}

    _save_cache(new_cache)
    elapsed = time.monotonic() - start
    print(f"[cython] Scanned {len(candidates)} modules in {elapsed:.2f}s"
          f" ({cache_hits} cached)")

    return extensions, skipped


def main():
    extensions, skipped = collect_extensions()
    total = len(extensions) + len(skipped)
    print(f"[cython] {len(extensions)}/{total} modules to compile"
          f" ({len(skipped)} skipped)")
    if skipped:
        for s in skipped:
            print(f"  skip: {s}")

    if not extensions:
        print("[cython] No compilable modules found")
        sys.exit(0)

    setup(
        name="ofx",
        ext_modules=cythonize(
            extensions,
            compiler_directives={
                "language_level": "3",
                "boundscheck": False,
                "wraparound": False,
                # annotation_typing MUST be False — OFX uses Python type hints
                # for documentation/mypy, not Cython C-type declarations.
                # Enabling it causes Cython to reject dict subclasses
                # (e.g., _StepAccessor) assigned to `dict[str, Any]` locals.
                "annotation_typing": False,
            },
            nthreads=os.cpu_count() or 4,
            quiet=False,
        ),
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        package_data={
            "ofx": [
                "data/**/*",
                "data/**/**/*",
            ],
        },
        zip_safe=False,
    )


if __name__ == "__main__":
    main()
