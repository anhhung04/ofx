"""Declared tool modules (``local.tool.*``).

Each module wraps one external binary with explicit typed inputs. Tools are
declared per-binary so workflows read ``module: local.tool.dalfox`` rather
than a generic scan runner with a raw argv. Modules are self-contained (no
``ofx.*`` imports) so remote execution can stream them like builtins.
"""

from ofx.modules.tools import dalfox as _dalfox
from ofx.modules.tools import dirsearch as _dirsearch
from ofx.modules.tools import ffuf as _ffuf
from ofx.modules.tools import sqlmap as _sqlmap
from ofx.modules.tools import tplmap as _tplmap

TOOL_MODULES = (_dalfox, _dirsearch, _ffuf, _sqlmap, _tplmap)

__all__ = ["TOOL_MODULES"]
