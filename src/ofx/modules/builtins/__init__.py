"""Builtin OFX modules."""

from ofx.modules.builtins import classify as _classify
from ofx.modules.builtins import merge as _merge
from ofx.modules.builtins import normalize as _normalize
from ofx.modules.builtins import python as _python
from ofx.modules.builtins import shell as _shell

BUILTIN_MODULES = (_shell, _python, _merge, _normalize, _classify)

__all__ = ["BUILTIN_MODULES"]
