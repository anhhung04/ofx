"""OFX API modules for red teaming operations.

Lazy-loaded modules for optimal performance.
Modules are imported on first access to reduce startup time.
"""

import sys
from typing import Any

# Track what's being loaded to prevent recursion
_loading = set()

def __getattr__(name: str) -> Any:
    """Lazy load API modules on demand."""
    if name in _loading:
        raise AttributeError(f"Circular import detected for 'ofx.api.{name}'")
    
    _loading.add(name)
    try:
        if name == "http":
            from ofx.api import http as module
        elif name == "file":
            from ofx.api import file as module
        elif name == "strings":
            from ofx.api import strings as module
        elif name == "network":
            from ofx.api import network as module
        elif name == "exploit":
            from ofx.api import exploit as module
        elif name == "httpserver":
            from ofx.api import httpserver as module
        elif name == "utils":
            from ofx.api import utils as module
        elif name == "oob":
            from ofx.api import oob as module
        elif name == "search":
            from ofx.api import search as module
        elif name == "shellcode":
            from ofx.api import shellcode as module
        elif name == "webshell":
            from ofx.api import webshell as module
        else:
            raise AttributeError(f"module 'ofx.api' has no attribute '{name}'")
        
        # Cache in sys.modules to prevent re-import
        setattr(sys.modules[__name__], name, module)
        return module
    finally:
        _loading.discard(name)

__all__ = [
    "http",
    "file",
    "strings",
    "network",
    "exploit",
    "httpserver",
    "utils",
    "oob",
    "search",
    "shellcode",
    "webshell",
]
