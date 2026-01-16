import os
import tomllib
from pathlib import Path

from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py


def get_version_from_toml():
    # Adopt path to your pyproject.toml
    pyproject_toml_file = Path(__file__).parent / "pyproject.toml"
    if pyproject_toml_file.exists():
        with open(pyproject_toml_file, "rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    raise RuntimeError("pyproject.toml not found or version not specified")


def collect_data_files(root: Path) -> list[str]:
    """Enumerate data files while skipping cache and build artifacts."""
    files: list[str] = []
    exclude_suffixes = {".c"}

    for path in root.rglob("*"):
        if path.is_dir() or path.suffix in exclude_suffixes:
            continue

        rel = path.relative_to("src/ofx")
        if "__pycache__" in rel.parts:
            continue

        files.append(rel.as_posix())
    return files


EXCLUDE_DATA_PATH = Path("src/ofx/data")
EXCLUDE_FILES = [str(p) for p in EXCLUDE_DATA_PATH.rglob("*") if p.is_file()]
DATA_FILES = collect_data_files(EXCLUDE_DATA_PATH)


def get_ext_paths(root_dir, exclude_files):
    """Get filepaths for Cython compilation."""
    paths = []
    if os.environ.get("OFX_COMPILE") != "1":
        return paths

    for root, _, files in os.walk(root_dir):
        for filename in files:
            if not filename.endswith(".py") or "__pycache__" in root:
                continue

            file_path = os.path.join(root, filename)
            if file_path in exclude_files or filename == "__init__.py":
                continue

            paths.append(file_path)
    return paths


class build_py(_build_py):
    """Custom build_py to exclude .py files that are being replaced by compiled extensions."""

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        filtered_modules = []
        for pkg, mod, filepath in modules:
            c_file = filepath.replace(".py", ".c")
            if os.path.exists(c_file):
                continue
            filtered_modules.append((pkg, mod, filepath))
        return filtered_modules


setup(
    name="ofx",
    version=get_version_from_toml(),
    packages=find_packages(where="src"),
    include_package_data=True,
    ext_modules=cythonize(
        get_ext_paths("src/ofx", EXCLUDE_FILES),
        compiler_directives={
            "language_level": "3",
            "always_allow_keywords": True,
        },
        nthreads=os.cpu_count() or 1,
    ),
    cmdclass={
        "build_py": build_py,
    },
    package_dir={"": "src"},
    package_data={"ofx": DATA_FILES},
    exclude_package_data={
        "": ["*.c", "*.pyd"],
    },
    zip_safe=True,
)
