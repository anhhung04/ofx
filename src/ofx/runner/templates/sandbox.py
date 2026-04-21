"""Sandboxed Jinja2 template rendering for OFX workflows.

Every workflow-sourced template string passes through this module.  The
sandbox blocks access to Python internals (dunder attributes, ``os``,
``subprocess``, etc.) while keeping the full set of OFX template helpers
available.
"""

from __future__ import annotations

import logging
import os as _os
import subprocess as _subprocess
import types
from typing import Any

from jinja2 import Undefined
from jinja2.sandbox import SandboxedEnvironment

_logger = logging.getLogger("ofx.templates")

# Attributes that must never be reachable from a template expression.
_UNSAFE_ATTRS: frozenset[str] = frozenset(
    {
        "__class__",
        "__bases__",
        "__mro__",
        "__subclasses__",
        "__init__",
        "__globals__",
        "__builtins__",
        "__import__",
        "__code__",
        "__func__",
        "__self__",
        "__module__",
        "__dict__",
        "__delattr__",
        "__setattr__",
        "__getattr__",
        "__reduce__",
        "__reduce_ex__",
        "__qualname__",
        "__wrapped__",
        "__loader__",
        "__spec__",
        "__path__",
        "__file__",
        "__cached__",
        "__package__",
        # subprocess / os / sys access guards
        "gi_frame",
        "gi_code",
        "f_locals",
        "f_globals",
        "f_builtins",
        "co_consts",
        "tb_frame",
    }
)

# Modules whose *instances* should never appear as template variables.
# We check by module name to avoid importing them.
_BLOCKED_MODULE_PREFIXES: tuple[str, ...] = (
    "os",
    "posix",
    "nt",
    "subprocess",
    "sys",
    "importlib",
    "builtins",
    "shutil",
    "signal",
    "ctypes",
    "code",
    "codeop",
    "compileall",
    "_io",
    "io",
)

# Specific callables that must never be invoked from templates.
_BLOCKED_CALLABLES: frozenset = frozenset(
    {
        eval,
        exec,
        compile,
        __import__,
        getattr,
        setattr,
        delattr,
        _os.system,
        _os.popen,
        _os.execl if hasattr(_os, "execl") else None,
        _os.execle if hasattr(_os, "execle") else None,
        _os.execlp if hasattr(_os, "execlp") else None,
        _os.execv if hasattr(_os, "execv") else None,
        _os.execve if hasattr(_os, "execve") else None,
        _os.execvp if hasattr(_os, "execvp") else None,
        _os.fork if hasattr(_os, "fork") else None,
        _os.forkpty if hasattr(_os, "forkpty") else None,
        _os.kill if hasattr(_os, "kill") else None,
        _os.killpg if hasattr(_os, "killpg") else None,
        _os.remove,
        _os.unlink,
        _os.rmdir,
        _os.rename,
        _os.replace,
        _os.chmod,
        _os.chown if hasattr(_os, "chown") else None,
        _subprocess.run,
        _subprocess.call,
        _subprocess.check_call,
        _subprocess.check_output,
        _subprocess.Popen,
        open,
    }
) - {None}


class _OFXSandboxedEnvironment(SandboxedEnvironment):
    """Jinja2 sandbox with OFX-specific restrictions."""

    def is_safe_attribute(self, obj: Any, attr: str, value: Any) -> bool:
        """Block dunder and other unsafe attribute access."""
        if attr in _UNSAFE_ATTRS:
            return False
        if attr.startswith("__") and attr.endswith("__"):
            return False
        # Block attribute access on module objects from blocked prefixes
        if isinstance(obj, types.ModuleType):
            obj_name = getattr(obj, "__name__", "") or ""
            if any(obj_name == p or obj_name.startswith(p + ".") for p in _BLOCKED_MODULE_PREFIXES):
                return False
        return super().is_safe_attribute(obj, attr, value)

    def is_safe_callable(self, obj: Any) -> bool:
        """Prevent calling dangerous builtins from templates."""
        if obj in _BLOCKED_CALLABLES:
            return False
        mod = getattr(obj, "__module__", "") or ""
        if any(mod == p or mod.startswith(p + ".") for p in _BLOCKED_MODULE_PREFIXES):
            return False
        return super().is_safe_callable(obj)

    def getattr(self, obj: Any, attribute: str) -> Any:
        """Override getattr to enforce dunder blocking before lookup."""
        if attribute in _UNSAFE_ATTRS or (
            attribute.startswith("__") and attribute.endswith("__")
        ):
            return Undefined(
                hint=f"access to '{attribute}' is restricted",
                name=attribute,
            )
        return super().getattr(obj, attribute)


def build_sandboxed_env(*, enable_async: bool = True) -> _OFXSandboxedEnvironment:
    """Build the singleton-safe sandboxed Jinja2 environment.

    The returned environment:
    - Uses ``SandboxedEnvironment`` with custom ``is_safe_attribute``
    - Blocks all dunder attribute access
    - Blocks calls to ``eval``, ``exec``, ``compile``, ``__import__``,
      ``getattr``, ``setattr``, ``delattr``
    - Blocks callable objects from ``os``, ``subprocess``, ``sys``, etc.
    - Does NOT enable ``autoescape`` (wrong for shell command contexts)
    - Does NOT load ``jinja2.ext.do`` extension
    - Does NOT support ``{% include %}`` or ``{% import %}`` (no loader)
    """
    env = _OFXSandboxedEnvironment(enable_async=enable_async)
    return env
