"""Wrapper source generation for remote UDF and ``ofx.api`` module steps.

The wrapper is a self-contained Python program that is bundled (see
:mod:`ofx.cloud.payload`) and executed on the remote host: it rebuilds the
step inputs/secrets into a minimal ``ModuleContext``, invokes the target, and
prints the base64-encoded outputs sentinel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ofx.cloud.module_source import (
    resolve_api_step_target,
    resolve_udf_source,
    resolve_udf_target,
)
from ofx.models.step import Step

# Canonical kwargs shim embedded in the ``ofx.api`` wrapper.
#
# The wrapper cannot import ``ofx.modules.api.invoke_api_callable``: module
# bundles only ever collect ``ofx.api.*`` sources (``KNOWN_API_MODULES`` in
# ofx/api/bundle/analyzer.py; collector.collect_modules resolves paths under
# ``ofx/api/``), and ``ofx.modules`` transitively imports ``ofx.runner`` — far
# too much to ship to a remote host. The shim is therefore extracted from this
# single constant (no hand-copied duplicates) and covered by a parity test
# against ``invoke_api_callable`` (see tests/test_udf_wrapper_shim.py).
INVOKE_KWARGS_SHIM = '''\
def _invoke_kwargs(_func, _args):
    # Mirrors ofx.modules.api.invoke_api_callable: filter the step args to the
    # function signature so unrelated workflow inputs are ignored.
    _params = _inspect.signature(_func).parameters
    if any(_p.kind is _inspect.Parameter.VAR_KEYWORD for _p in _params.values()):
        return _func(**_args)
    _kwargs = {}
    _missing = []
    for _name, _param in _params.items():
        if _param.kind in (
            _inspect.Parameter.VAR_POSITIONAL,
            _inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if _name in _args:
            _kwargs[_name] = _args[_name]
        elif _param.default is _inspect.Parameter.empty:
            _missing.append(_name)
    if _missing:
        raise TypeError(
            "missing required argument(s) "
            + ", ".join(_missing)
            + "; received keys: "
            + (", ".join(sorted(_args)) or "(none)")
        )
    return _func(**_kwargs)
'''

_UDF_WRAPPER_TEMPLATE = '''\
# ofx remote UDF wrapper (generated)
import base64 as _b64, json as _json, os as _os, sys as _sys, traceback as _tb

_UDF_SOURCE = {source!r}
_UDF_FUNCTION = {function!r}
_UDF_INPUTS = _json.loads({inputs_json!r})
_UDF_SECRETS = _json.loads({secrets_json!r})

class _ModuleContext:
    def __init__(self):
        self.inputs = _UDF_INPUTS
        self.secrets = _UDF_SECRETS
        self.env = dict(_os.environ)
        self.working_directory = _os.getcwd()
        self._outputs = {{}}
    def add_outputs(self, **kwargs):
        self._outputs.update(kwargs)
    def log(self, message):
        print(f"[module] {{message}}", file=_sys.stderr)

_ns = {{"__name__": "__ofx_udf__"}}
exec(compile(_UDF_SOURCE, "<udf>", "exec"), _ns)
_func = _ns[_UDF_FUNCTION]
_ctx = _ModuleContext()
try:
    _result = _func(_ctx)
    if isinstance(_result, dict):
        _ctx._outputs.update(_result)
    _outputs = _ctx._outputs
    _code = 0
except Exception:
    _tb.print_exc()
    _outputs = {{}}
    _code = 1
print("__OFX_MODULE_OUTPUTS__" + _b64.b64encode(
    _json.dumps(_outputs, default=str).encode()).decode())
_sys.exit(_code)
'''

_API_UDF_WRAPPER_TEMPLATE = '''\
# ofx remote UDF wrapper (generated)
import base64 as _b64, inspect as _inspect, json as _json, os as _os, sys as _sys, traceback as _tb

from ofx.api.{api_module} import {api_attr} as _func

_UDF_INPUTS = _json.loads({inputs_json!r})
_UDF_SECRETS = _json.loads({secrets_json!r})
_UDF_CTX_STYLE = {ctx_style!r}

class _ModuleContext:
    def __init__(self):
        self.inputs = _UDF_INPUTS
        self.secrets = _UDF_SECRETS
        self.env = dict(_os.environ)
        self.working_directory = _os.getcwd()
        self._outputs = {{}}
    def add_outputs(self, **kwargs):
        self._outputs.update(kwargs)
    def log(self, message):
        print(f"[module] {{message}}", file=_sys.stderr)

{shim}
_ctx = _ModuleContext()
try:
    _result = _func(_ctx) if _UDF_CTX_STYLE else _invoke_kwargs(_func, _UDF_INPUTS)
    if isinstance(_result, dict):
        _ctx._outputs.update(_result)
    elif _result is not None:
        _ctx._outputs["result"] = _result
    _outputs = _ctx._outputs
    _code = 0
except Exception:
    _tb.print_exc()
    _outputs = {{}}
    _code = 1
print("__OFX_MODULE_OUTPUTS__" + _b64.b64encode(
    _json.dumps(_outputs, default=str).encode()).decode())
_sys.exit(_code)
'''


def build_udf_step_source(
    step: Step,
    *,
    workflow_dir: Path | None = None,
    inputs: dict[str, Any] | None = None,
    secrets: dict[str, Any] | None = None,
) -> str:
    """Render the remote wrapper source for a ``module:`` UDF step.

    UDF targets embed the module file source. ``ofx.api`` targets (a
    ``local.api.<path>`` step or a remote manifest entry declared with
    ``api:``) instead import the function by path — real source text, so the
    bundle analyzer picks up its ``ofx.api`` imports automatically — and carry
    an inline kwargs shim mirroring
    :func:`ofx.modules.api.invoke_api_callable`.

    Either way the wrapper resolves *inputs*/*secrets* (JSON-serialized with
    ``default=str``) into a minimal ``ModuleContext``, invokes the target
    function, and prints a ``__OFX_MODULE_OUTPUTS__`` sentinel line
    (base64-encoded JSON) as its final stdout output.
    """
    inputs_json = json.dumps(dict(inputs or {}), default=str)
    secrets_json = json.dumps(dict(secrets or {}), default=str)
    api_path = resolve_api_step_target(step, workflow_dir=workflow_dir)
    if api_path is not None:
        return _build_api_udf_step_source(
            api_path,
            inputs_json=inputs_json,
            secrets_json=secrets_json,
        )
    _path, function = resolve_udf_target(step, workflow_dir=workflow_dir)
    source = resolve_udf_source(step, workflow_dir=workflow_dir)
    return _UDF_WRAPPER_TEMPLATE.format(
        source=source,
        function=function,
        inputs_json=inputs_json,
        secrets_json=secrets_json,
    )


def _build_api_udf_step_source(
    api_path: str, *, inputs_json: str, secrets_json: str
) -> str:
    """Render the remote wrapper source for an ``ofx.api``-backed step."""
    # Imported lazily to avoid the ofx.modules/ofx.runner import cycle.
    from ofx.modules.api import is_ctx_style, resolve_api_callable, resolve_api_import

    api_module, api_attr = resolve_api_import(api_path)
    return _API_UDF_WRAPPER_TEMPLATE.format(
        api_module=api_module.removeprefix("ofx.api."),
        api_attr=api_attr,
        ctx_style=is_ctx_style(resolve_api_callable(api_path)),
        inputs_json=inputs_json,
        secrets_json=secrets_json,
        shim=INVOKE_KWARGS_SHIM,
    )


__all__ = ["INVOKE_KWARGS_SHIM", "build_udf_step_source"]
