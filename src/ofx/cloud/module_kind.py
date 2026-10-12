"""Classification of workflow steps into module kinds.

A remote step is either a builtin ``python`` module step, a builtin ``shell``
module step, or a UDF-like step (file UDF, workflow-local named module,
``ofx.api`` function, or remote GitHub module) whose source is bundled.
"""

from __future__ import annotations

from ofx.models.step import Step

MODULE_PYTHON_NAMES: frozenset[str] = frozenset(
    {"python", "builtin.python", "local.builtin.python"}
)
MODULE_SHELL_NAMES: frozenset[str] = frozenset(
    {"shell", "builtin.shell", "local.builtin.shell"}
)


def module_base_name(module: str | None) -> str:
    """Return the base module name without a ``::func`` UDF suffix."""
    if not module:
        return ""
    return module.split("::", 1)[0]


def is_python_module_step(step: Step) -> bool:
    """Return whether a step invokes the builtin python module."""
    return module_base_name(getattr(step, "module", None)) in MODULE_PYTHON_NAMES


def is_shell_module_step(step: Step) -> bool:
    """Return whether a step invokes the builtin shell module."""
    return module_base_name(getattr(step, "module", None)) in MODULE_SHELL_NAMES


def is_udf_module_step(step: Step) -> bool:
    """Return whether a step invokes a user-defined module (UDF).

    UDF specs use ``<file>.py`` or ``<file>.py::<function>`` form; local
    named modules (``local.<name>``), ``ofx.api`` functions
    (``local.builtin.<path>``) and remote GitHub modules
    (``<owner>.<repo>.<module>[@<ref>][::<func>]``) are UDF-like too —
    their source is bundled for remote execution. Pure-Python builtins
    (anything in the builtin registry except shell/python) are also
    bundled: their source lives under ``ofx/modules/builtins/``.
    Builtin python/shell module steps are never UDFs, even when their
    spec contains ``::`` or ends in ``.py``.
    """
    module = getattr(step, "module", None) or ""
    if not module:
        return False
    base = module_base_name(module)
    if base in MODULE_PYTHON_NAMES or base in MODULE_SHELL_NAMES:
        return False
    # Imported lazily: ofx.modules transitively pulls in ofx.runner, which
    # imports this module — an eager import would cycle.
    from ofx.modules.refs import (
        API_KIND,
        BUILTIN_KIND,
        LOCAL_NAMED_KIND,
        REMOTE_KIND,
        TOOL_KIND,
        parse_module_ref,
    )

    try:
        kind = parse_module_ref(base).kind
    except ValueError:
        kind = None
    if kind in (LOCAL_NAMED_KIND, REMOTE_KIND, API_KIND, BUILTIN_KIND, TOOL_KIND):
        return True
    return "::" in module or module.endswith(".py")


__all__ = [
    "MODULE_PYTHON_NAMES",
    "MODULE_SHELL_NAMES",
    "is_python_module_step",
    "is_shell_module_step",
    "is_udf_module_step",
    "module_base_name",
]
