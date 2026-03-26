"""Cython compilation script for OFX.

Compiles all Python modules under src/ofx/ into C extensions (.so on Linux,
.pyd on Windows) for performance and source code protection.

Usage:
    python setup_cython.py build_ext --inplace
    # Or via Makefile:
    make compile

Files with syntax unsupported by Cython are auto-detected via a dry-run
compilation pass and excluded — they remain as .py files.
"""

import io
import os
import re
import sys
from pathlib import Path

from Cython.Build import cythonize
from Cython.Compiler.Main import compile as cython_compile
from Cython.Compiler.Options import CompilationOptions
from setuptools import Extension, find_packages, setup

SRC_DIR = Path("src")
PACKAGE_DIR = SRC_DIR / "ofx"

EXCLUDE_PATTERNS = {
    "__init__.py",  # package discovery
    "_version.py",  # importlib.metadata at import
    "conftest.py",  # pytest
}

EXCLUDE_DIRS = {
    "data",  # YAML workflows, static site
    "commands",  # Typer CLI — relies on signature introspection
    "models",  # Pydantic models — validators break under Cython
    "__pycache__",
}

# Files with Pydantic BaseModel subclasses (validators become cyfunction,
# which Pydantic rejects as unannotated attributes)
_PYDANTIC_MARKERS = re.compile(
    r"class\s+\w+\(.*(?:BaseModel|OFXBaseModel|BaseSettings).*\):",
    re.MULTILINE,
)

# @staticmethod + @lru_cache combo breaks under Cython
_STATIC_LRU_COMBO = re.compile(
    r"@staticmethod\s+@lru_cache|@lru_cache.*\s+@staticmethod",
    re.MULTILINE,
)


def _can_cythonize(path: Path) -> bool:
    """Try-compile a file to check if Cython can handle it."""
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        result = cython_compile(
            str(path), CompilationOptions(language_level=3)
        )
        return result.num_errors == 0
    except Exception:
        return False
    finally:
        sys.stderr = old_stderr
        # Clean up generated .c file from dry run
        c_file = path.with_suffix(".c")
        if c_file.exists():
            c_file.unlink()


def collect_extensions() -> tuple[list[Extension], list[str]]:
    """Walk src/ofx/ and create Extension objects for compilable .py files."""
    candidates = []
    for py_file in sorted(PACKAGE_DIR.rglob("*.py")):
        if py_file.name in EXCLUDE_PATTERNS:
            continue
        if any(part in EXCLUDE_DIRS for part in py_file.parts):
            continue
        candidates.append(py_file)

    print(f"[cython] Checking {len(candidates)} modules for compatibility...")

    extensions = []
    skipped: list[str] = []

    for py_file in candidates:
        # Fast check: skip files with Pydantic models
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            skipped.append(str(py_file))
            continue

        if _PYDANTIC_MARKERS.search(text):
            skipped.append(str(py_file))
            continue

        if _STATIC_LRU_COMBO.search(text):
            skipped.append(str(py_file))
            continue

        if _can_cythonize(py_file):
            rel = py_file.relative_to(SRC_DIR)
            module_name = str(rel.with_suffix("")).replace(os.sep, ".")
            extensions.append(Extension(module_name, [str(py_file)]))
        else:
            skipped.append(str(py_file))

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
                "annotation_typing": True,
            },
            nthreads=os.cpu_count() or 4,
            quiet=False,
        ),
        packages=find_packages(where="src"),
        package_dir={"": "src"},
        zip_safe=False,
    )


if __name__ == "__main__":
    main()
