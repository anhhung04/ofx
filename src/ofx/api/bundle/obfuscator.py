"""Obfuscate a Python bootstrap script using marshal + XOR encryption.

Compiles the bootstrap to a CPython code object, serialises it with
:mod:`marshal`, XOR-encrypts the bytecode with a random key, and wraps
everything in a tiny self-contained loader stub.  The result is a valid
Python file that decrypts and executes the original code in-memory with no
temporary files or external dependencies.

Why marshal + XOR?
- No third-party dependencies needed on the remote target.
- Bytecode is harder to casually read than source; XOR prevents simple grep.
- The loader is short enough to be inconspicuous.

:func:`obfuscate_sources` compiles every ``.py`` file in a collected-modules
dict to a marshalled code object and replaces the source with a compact stub.
The stub executes in the module's own namespace so all names are populated
normally — import behaviour is unchanged.  Useful for protecting tool source
from being read by other parties (e.g. opposing teams in a cyber-range contest).
"""

from __future__ import annotations

import marshal
import os
import types

from .analyzer import BundleError

__all__ = ["ObfuscationError", "obfuscate_bootstrap", "obfuscate_sources"]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ObfuscationError(BundleError):
    """Raised when the obfuscation step fails."""


# ---------------------------------------------------------------------------
# Loader template
#
# Intentionally kept short and variable-name-free of obvious identifiers.
# Use !r / hex strings so no bytes need escaping in the rendered output.
# ---------------------------------------------------------------------------

_LOADER_TEMPLATE = """\
import marshal as _m
_k=bytes.fromhex({key_hex!r})
_e=bytes.fromhex({enc_hex!r})
_d=bytes(a^_k[i%len(_k)]for i,a in enumerate(_e))
exec(_m.loads(_d))
"""

# Per-source-file encrypted stub: compile → marshal → XOR → hex.
# Same scheme as the bootstrap loader, applied per module.  exec() at module
# scope without an explicit globals dict uses the calling frame's globals,
# which is the module's own __dict__ — so all defs/assignments land in the
# right place and imports work normally.
_SOURCE_STUB_TEMPLATE = """\
import marshal as _m
_k=bytes.fromhex({key_hex!r})
_e=bytes.fromhex({enc_hex!r})
exec(_m.loads(bytes(a^_k[i%len(_k)]for i,a in enumerate(_e))))
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_code(code, *, _generic: str = "<module>") -> types.CodeType:
    """Recursively strip identifying metadata from a code object.

    Removes:
    - ``co_filename`` → replaced with a generic label
    - Leading-string docstrings in ``co_consts`` → replaced with ``None``
    - Nested code objects are processed recursively

    Returns a new code object; the original is not mutated.
    """
    new_consts: list[object] = []
    for i, c in enumerate(code.co_consts):
        if hasattr(c, "co_code"):
            # Nested code object (function/class body) — recurse
            new_consts.append(_strip_code(c, _generic=_generic))
        elif i == 0 and isinstance(c, str):
            # First const is the docstring by convention — strip it
            new_consts.append(None)
        else:
            new_consts.append(c)

    return code.replace(
        co_filename=_generic,
        co_consts=tuple(new_consts),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def obfuscate_sources(files: dict[str, bytes]) -> dict[str, bytes]:
    """Compile every ``.py`` file in *files* to marshalled, XOR-encrypted bytecode.

    Each ``.py`` source is:

    1. Compiled to a CPython code object.
    2. Stripped of identifying metadata (filenames, docstrings).
    3. Serialised with :mod:`marshal`.
    4. XOR-encrypted with a per-file random 16-byte key.
    5. Wrapped in a compact loader stub that decrypts and ``exec()``s at import.

    Non-``.py`` entries are passed through unchanged.

    The transformed dict is drop-in compatible with :func:`~.builder.build_bundle`
    — the ``.py`` extensions are kept so Python's import machinery still finds
    the modules.

    Args:
        files: Mapping of archive-relative POSIX paths to file bytes, as
            returned by :func:`~.collector.collect_modules`.

    Returns:
        New dict with the same keys; ``.py`` values replaced by encrypted stubs.

    Raises:
        ObfuscationError: If any source file fails to compile or marshal.
    """
    result: dict[str, bytes] = {}
    for path, raw in files.items():
        if not path.endswith(".py"):
            result[path] = raw
            continue
        key = os.urandom(16)
        try:
            code = compile(raw, path, "exec")
            code = _strip_code(code)
            raw_bytes = marshal.dumps(code)
        except Exception as exc:
            raise ObfuscationError(
                f"Failed to compile/marshal source {path!r}: {exc}"
            ) from exc
        enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw_bytes))
        stub = _SOURCE_STUB_TEMPLATE.format(key_hex=key.hex(), enc_hex=enc.hex())
        result[path] = stub.encode()
    return result


def obfuscate_bootstrap(bootstrap: str, *, key: bytes | None = None) -> str:
    """Compile *bootstrap* to bytecode, XOR-encrypt it, and return a loader.

    The returned string is a valid Python script that re-creates and executes
    the original code entirely in memory.

    Args:
        bootstrap: Python source to obfuscate (typically the ``bootstrap``
            field of a :class:`~ofx.api.bundle.builder.BundleResult`).
        key: XOR key bytes.  A random 16-byte key is generated when *None*.

    Returns:
        Obfuscated loader script as a Python source string.

    Raises:
        ObfuscationError: If *bootstrap* fails to compile or marshal.
        ValueError: If an explicit *key* is empty.
    """
    if key is None:
        key = os.urandom(16)
    if not key:
        raise ValueError("XOR key must be non-empty")

    try:
        code = compile(bootstrap, "<bundle>", "exec")
        raw = marshal.dumps(code)
    except Exception as exc:
        raise ObfuscationError(f"Failed to compile/marshal bootstrap: {exc}") from exc

    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return _LOADER_TEMPLATE.format(key_hex=key.hex(), enc_hex=enc.hex())
