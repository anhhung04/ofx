# coding: utf-8
import os
import sys
import sysconfig
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "ofx")))

from _version import __version__
from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.build import build as _build


def collect_data_files(root: Path) -> list[str]:
    """Enumerate data files while skipping cache artifacts."""
    files: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to("src/ofx")
        if "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        files.append(rel.as_posix())
    return files


EXCLUDE_FILES = [str(p) for p in Path("src/ofx/data").rglob("*") if p.is_file()]
DATA_FILES = collect_data_files(Path("src/ofx/data"))


def get_ext_paths(root_dir, exclude_files):
    """get filepaths for compilation"""
    paths = []
    if os.environ.get("OFX_SKIP_CYTHONIZE") == "1":
        return paths

    for root, dirs, files in os.walk(root_dir):
        for filename in files:
            if os.path.splitext(filename)[1] != ".py" or "__pycache__" in root:
                continue

            file_path = os.path.join(root, filename)
            if file_path in exclude_files:
                continue

            paths.append(file_path)
    return paths


# Custom build_py to exclude .py files that have a compiled version
# noinspection PyPep8Naming
class build_py(_build_py):
    def find_package_modules(self, package, package_dir):
        ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
        modules = super().find_package_modules(package, package_dir)
        filtered_modules = []
        for pkg, mod, filepath in modules:
            if os.path.exists(filepath.replace(".py", ext_suffix)):
                continue
            filtered_modules.append(
                (
                    pkg,
                    mod,
                    filepath,
                )
            )
        return filtered_modules


class build(_build):
    # Force build_py to run so package_data is included even when only extensions exist
    def has_pure_modules(self):
        return True


setup(
    name="ofx",
    version=__version__,
    packages=find_packages(where="src"),
    include_package_data=True,
    ext_modules=cythonize(
        get_ext_paths("src/ofx", EXCLUDE_FILES),
        compiler_directives={
            "language_level": 3,
        },
        nthreads=os.cpu_count() or 1,
    ),
    # Register our custom commands
    cmdclass={
        "build_py": build_py,
        "build": build,
    },
    package_dir={"": "src"},
    package_data={"ofx": DATA_FILES},
    extra_compile_args=["-O3"],
)

for root, dirs, files in os.walk("src/ofx"):
    for filename in files:
        file = os.path.join(root, filename)
        if file.endswith(".c") or file.endswith(".so"):
            os.remove(file)
