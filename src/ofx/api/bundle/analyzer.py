"""AST-based detection of ofx.api.* imports used in a Python script."""

from __future__ import annotations

import ast
import warnings

__all__ = [
    "KNOWN_API_MODULES",
    "BundleError",
    "AnalysisError",
    "detect_ofx_imports",
]

# ---------------------------------------------------------------------------
# Known top-level ofx.api modules — derived from ofx/api/__init__.py __all__
# ---------------------------------------------------------------------------

KNOWN_API_MODULES: frozenset[str] = frozenset(
    {
        "ad",
        "c2",
        "creds",
        "data",
        "dns",
        "evasion",
        "exfil",
        "exploitation",
        "file",
        "http",
        "httpserver",
        "lateral",
        "loot",
        "network",
        "oob",
        "opsec",
        "packers",
        "payloads",
        "persistence",
        "post",
        "privesc",
        "recon",
        "search",
        "service",
        "strings",
        "utils",
        "bundle",
    }
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BundleError(Exception):
    """Base exception for all bundle operations."""


class AnalysisError(BundleError):
    """Raised when AST parsing or module analysis fails."""

    def __init__(self, message: str, *, source: str | None = None) -> None:
        self.source = source
        super().__init__(message)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _top_module_from_dotted(dotted: str) -> str | None:
    """Return the top-level ofx.api submodule name from a dotted import path.

    Examples::

        "ofx.api.opsec"           -> "opsec"
        "ofx.api.opsec.proxy"     -> "opsec"
        "ofx.api"                 -> None   (no submodule)
        "ofx"                     -> None
        "requests"                -> None
    """
    prefix = "ofx.api."
    if not dotted.startswith(prefix):
        return None
    rest = dotted[len(prefix):]
    if not rest:
        return None
    return rest.split(".")[0]


def _modules_from_node(node: ast.AST) -> set[str]:
    """Return ofx.api top-level module names referenced in a single AST node."""
    found: set[str] = set()

    if isinstance(node, ast.Import):
        # import ofx.api.opsec
        # import ofx.api.opsec.proxy
        for alias in node.names:
            top = _top_module_from_dotted(alias.name)
            if top:
                found.add(top)

    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""

        if module == "ofx.api":
            # from ofx.api import opsec, c2, ad
            for alias in node.names:
                found.add(alias.name)

        elif module.startswith("ofx.api."):
            # from ofx.api.opsec import clean_history_commands
            # from ofx.api.opsec.cleanup import clean_history_commands
            top = _top_module_from_dotted(module)
            if top:
                found.add(top)

    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_ofx_imports(
    script: str,
    *,
    extra_modules: list[str] | None = None,
    source_name: str = "<script>",
) -> set[str]:
    """Parse *script* and return the set of ``ofx.api`` submodule names used.

    Covers all four import patterns::

        import ofx.api.opsec
        from ofx.api import opsec, c2
        from ofx.api.opsec import clean_history_commands
        from ofx.api.opsec.cleanup import clean_history_commands

    All resolved names are validated against :data:`KNOWN_API_MODULES`.
    Unknown names are silently dropped (they may be user-defined modules
    that happen to share a name with an OFX module).

    Args:
        script: Python source code to analyse.
        extra_modules: Additional module names to always include,
            regardless of what the AST finds.  Invalid names emit a warning.
        source_name: Label used in error messages (e.g. a filename).

    Returns:
        Set of ``ofx.api`` top-level module names, e.g. ``{"opsec", "c2"}``.

    Raises:
        AnalysisError: If *script* cannot be parsed as valid Python.
    """
    # Parse
    try:
        tree = ast.parse(script, filename=source_name)
    except SyntaxError as exc:
        raise AnalysisError(
            f"Cannot parse script {source_name!r}: {exc}",
            source=source_name,
        ) from exc

    # Walk AST collecting all references
    found: set[str] = set()
    for node in ast.walk(tree):
        found |= _modules_from_node(node)

    # Validate against known modules (unknown names silently dropped)
    validated = found & KNOWN_API_MODULES

    # Merge extra_modules
    if extra_modules:
        for name in extra_modules:
            if name in KNOWN_API_MODULES:
                validated.add(name)
            else:
                warnings.warn(
                    f"extra_modules: {name!r} is not a known ofx.api module "
                    f"and will be ignored.",
                    stacklevel=2,
                )

    return validated
