# coding: utf-8
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "ofx")))

from setuptools import setup, find_packages
from _version import __version__

setup(
    name="ofx",
    version=__version__,
    packages=find_packages(where="src"),
    package_dir={"":"src"},
    package_data={
        "ofx": ["data/*.yml", "data/**/*.yml"],
    },
)
