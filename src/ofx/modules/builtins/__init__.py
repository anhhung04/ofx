"""Builtin OFX modules."""

from ofx.modules.builtins import python as _python
from ofx.modules.builtins import shell as _shell

BUILTIN_MODULES = (_shell, _python)

__all__ = ["BUILTIN_MODULES"]
