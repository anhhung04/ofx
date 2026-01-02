# coding: utf-8
import os
import sys
import sysconfig

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "ofx")))

from _version import __version__
from Cython.Build import cythonize
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py as _build_py


def get_exclude_files(root_dir):
    exclude_files = []
    for root, dirs, files in os.walk(root_dir):
        for filename in files:
            file_path = os.path.join(root, filename)
            exclude_files.append(file_path)
    return exclude_files


EXCLUDE_FILES = get_exclude_files("src/ofx/data")


def get_ext_paths(root_dir, exclude_files):
    """get filepaths for compilation"""
    return []
    paths = []

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


setup(
    name="ofx",
    version=__version__,
    packages=find_packages(),
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
    },
    package_dir={"": "src"},
    package_data={
        "ofx": ["data/*", "data/**/*"],
    },
    extra_compile_args=["-O3"],
)

for root, dirs, files in os.walk("src/ofx"):
    for filename in files:
        file = os.path.join(root, filename)
        if file.endswith(".c") or file.endswith(".so"):
            os.remove(file)
