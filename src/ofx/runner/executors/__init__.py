"""Compatibility package for executor modules.

Avoid eager imports here to prevent circular imports during runner bootstrap.
"""

from ofx.runner.executors.base import Executor

__all__ = ["Executor"]
