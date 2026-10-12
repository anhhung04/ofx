"""Calling ``ofx.api`` functions as workflow modules.

``local.builtin.<path>.<func>`` module refs (and remote manifest entries with an
``api:`` key) resolve to a plain function under :mod:`ofx.api`. Those functions
take ordinary keyword arguments rather than a :class:`~ofx.modules.base.ModuleContext`,
so the runner bridges the two calling conventions:

- functions with a ``ctx`` parameter (annotated :class:`ModuleContext`, or
  unannotated) are ctx-style and receive the module context;
- every other function is kwargs-style and receives the invocation args
  filtered to its signature (extras are ignored — the invocation args are the
  merged workflow inputs plus the step's ``with:`` args, so unrelated keys are
  expected).
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from typing import Any

from ofx.modules.base import ModuleContext

API_ROOT = "ofx.api"
CTX_PARAM_NAME = "ctx"

_VARIADIC_KINDS = (
    inspect.Parameter.VAR_POSITIONAL,
    inspect.Parameter.VAR_KEYWORD,
)


class ApiModuleError(ValueError):
    """Raised when an ``ofx.api`` module path cannot be resolved or invoked."""


def _invalid_path(path: str, dotted_path: str) -> ApiModuleError:
    return ApiModuleError(
        f"Invalid ofx.api path '{dotted_path}': '{path}' is not a valid dotted "
        f"'{API_ROOT}.<path>' reference (empty segments are not allowed)"
    )


def _segments(dotted_path: str) -> list[str]:
    path = (dotted_path or "").strip().strip(".")
    if not path:
        raise ApiModuleError(
            "Invalid ofx.api reference: path after "
            f"'{API_ROOT}.' cannot be empty (use "
            f"'local.builtin.<path>.<func>')"
        )
    segments = path.split(".")
    if any(not segment for segment in segments):
        raise _invalid_path(path, dotted_path)
    return segments


def resolve_api_import(dotted_path: str) -> tuple[str, str]:
    """Return ``(module_path, attribute)`` for an ``ofx.api`` dotted path.

    Longest-prefix resolution: for ``recon.targets.split_targets`` this returns
    ``("ofx.api.recon.targets", "split_targets")``; for the shorthand
    ``recon.crtsh_subdomains`` (re-exported by ``ofx.api.recon``) it returns
    ``("ofx.api.recon", "crtsh_subdomains")``.

    Raises:
        ApiModuleError: If no importable module prefix exposes a callable at
            the remaining attribute path.
    """
    segments = _segments(dotted_path)
    attempts: list[str] = []
    for split in range(len(segments), 0, -1):
        module_path = ".".join([API_ROOT, *segments[:split]])
        attrs = segments[split:]
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:  # noqa: BLE001 - reported below
            attempts.append(f"{module_path} (import failed: {exc})")
            continue
        obj: Any = module
        for attr in attrs:
            try:
                obj = getattr(obj, attr)
            except AttributeError:
                attempts.append(
                    f"{module_path}.{'.'.join(attrs)} (no attribute '{attr}')"
                )
                break
        else:
            if not callable(obj):
                label = (
                    f"{module_path}.{'.'.join(attrs)}" if attrs else module_path
                )
                attempts.append(f"{label} (not callable)")
                continue
            return module_path, ".".join(attrs)
    target = ".".join([API_ROOT, *segments])
    raise ApiModuleError(
        f"Cannot resolve ofx.api function '{target}'. Tried: "
        + "; ".join(attempts)
    )


def resolve_api_callable(dotted_path: str) -> Callable[..., Any]:
    """Resolve an ``ofx.api.<path>`` dotted path to a callable.

    Tries the full path as a module, then progressively shorter module paths
    with the remaining segments looked up as module attributes, so both
    ``recon.targets.split_targets`` and shorthand re-exports such as
    ``recon.crtsh_subdomains`` resolve.

    Raises:
        ApiModuleError: If nothing callable matches; the message lists every
            attempted import.
    """
    module_path, attribute = resolve_api_import(dotted_path)
    module = importlib.import_module(module_path)
    obj: Any = module
    for attr in attribute.split("."):
        obj = getattr(obj, attr)
    return obj


def _annotates_module_context(annotation: Any) -> bool:
    """Return whether *annotation* refers to :class:`ModuleContext`."""
    if annotation is inspect.Parameter.empty:
        return False
    if isinstance(annotation, str):
        # Peeling quotes handles both a bare forward reference (``ctx:
        # "ModuleContext"``) and its literal form under ``from __future__
        # import annotations`` (``'"ModuleContext"'``).
        return annotation.strip("\"'").rsplit(".", 1)[-1] == ModuleContext.__name__
    return isinstance(annotation, type) and issubclass(annotation, ModuleContext)


def is_ctx_style(func: Callable[..., Any]) -> bool:
    """Return whether *func* takes a ``ctx`` (ModuleContext) argument.

    A parameter named ``ctx`` marks the function as ctx-style when it is
    unannotated or annotated with :class:`ModuleContext` (or a forward
    reference to it); anything else is treated as kwargs-style.
    """
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    for name, parameter in parameters.items():
        if name != CTX_PARAM_NAME:
            continue
        if parameter.annotation is inspect.Parameter.empty:
            return True
        return _annotates_module_context(parameter.annotation)
    return False


def _describe(func: Callable[..., Any]) -> str:
    module = getattr(func, "__module__", None) or ""
    qualname = getattr(func, "__qualname__", None) or getattr(func, "__name__", "")
    return f"{module}.{qualname}".lstrip(".") or repr(func)


def invoke_api_callable(
    func: Callable[..., Any], args: dict[str, Any] | None = None
) -> Any:
    """Call a kwargs-style ``ofx.api`` function with filtered invocation args.

    Arguments are filtered to the function's signature: extra keys (workflow
    inputs, unrelated step args) are ignored, and a function taking
    ``**kwargs`` receives everything. Missing required parameters raise
    :class:`ApiModuleError` naming both the missing parameters and the
    received keys.

    Raises:
        ApiModuleError: If a required parameter is not provided.
    """
    provided = dict(args or {})
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return func(**provided)

    if any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return func(**provided)

    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, parameter in parameters.items():
        if parameter.kind in _VARIADIC_KINDS:
            continue
        if name in provided:
            kwargs[name] = provided[name]
        elif parameter.default is inspect.Parameter.empty:
            missing.append(name)
    if missing:
        received = ", ".join(sorted(provided)) or "(none)"
        raise ApiModuleError(
            f"Missing required argument(s) for ofx.api function "
            f"'{_describe(func)}': {', '.join(missing)}. Received keys: "
            f"{received}"
        )
    return func(**kwargs)


__all__ = [
    "API_ROOT",
    "CTX_PARAM_NAME",
    "ApiModuleError",
    "invoke_api_callable",
    "is_ctx_style",
    "resolve_api_callable",
    "resolve_api_import",
]
