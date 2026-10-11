"""Shared Python step runtime helpers for cloud runner and sessions."""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ofx.api.bundle import build_bundle
from ofx.api.bundle.analyzer import detect_ofx_imports
from ofx.api.bundle.obfuscator import obfuscate_bootstrap
from ofx.models.step import RunType, Step

_MODULE_PYTHON_NAMES: frozenset[str] = frozenset(
    {"python", "builtin.python", "local.builtin.python"}
)
_MODULE_SHELL_NAMES: frozenset[str] = frozenset(
    {"shell", "builtin.shell", "local.builtin.shell"}
)

_MODULE_OUTPUTS_SENTINEL = "__OFX_MODULE_OUTPUTS__"

def module_base_name(module: str | None) -> str:
    """Return the base module name without a ``::func`` UDF suffix."""
    if not module:
        return ""
    return module.split("::", 1)[0]

def is_python_module_step(step: Step) -> bool:
    """Return whether a step invokes the builtin python module."""
    return module_base_name(getattr(step, "module", None)) in _MODULE_PYTHON_NAMES

def is_shell_module_step(step: Step) -> bool:
    """Return whether a step invokes the builtin shell module."""
    return module_base_name(getattr(step, "module", None)) in _MODULE_SHELL_NAMES

def is_udf_module_step(step: Step) -> bool:
    """Return whether a step invokes a user-defined module (UDF).

    UDF specs use ``<file>.py`` or ``<file>.py::<function>`` form; local
    named modules (``local.<name>``), ``ofx.api`` functions
    (``local.api.<path>``) and remote GitHub modules
    (``<owner>.<repo>.<module>[@<ref>][::<func>]``) are UDF-like too —
    their source is bundled for remote execution. Builtin python/shell
    module steps are never UDFs, even when their spec contains ``::`` or
    ends in ``.py``.
    """
    module = getattr(step, "module", None) or ""
    if not module:
        return False
    base = module_base_name(module)
    if base in _MODULE_PYTHON_NAMES or base in _MODULE_SHELL_NAMES:
        return False
    # Imported lazily: ofx.modules transitively pulls in ofx.runner, which
    # imports this module — an eager import would cycle.
    from ofx.modules.refs import (
        API_KIND,
        LOCAL_NAMED_KIND,
        REMOTE_KIND,
        parse_module_ref,
    )

    try:
        kind = parse_module_ref(base).kind
    except ValueError:
        kind = None
    if kind in (LOCAL_NAMED_KIND, REMOTE_KIND, API_KIND):
        return True
    return "::" in module or module.endswith(".py")

def resolve_python_step_source(step: Step, *, workflow_dir: Path | None = None) -> str:
    """Resolve Python source for a ``module: python`` step.

    The inline script is taken from the step's ``with:`` args
    (``run_with["script"]``); a ``script_file`` arg is read and returned
    when no inline script is given. Mirrors the legacy ``script``/``script_file``
    step kinds, which module steps replace.
    """
    run_type = step.get_run_type()
    if run_type != RunType.MODULE:
        raise ValueError(
            f"Unsupported step run type for python source resolution: {run_type}"
        )
    if not is_python_module_step(step):
        raise ValueError(
            f"Step '{step.name}' is not a python module step: {step.module!r}"
        )
    args = step.run_with or {}
    script = str(args.get("script") or "")
    if script:
        return script
    script_file = args.get("script_file")
    if not script_file:
        raise ValueError(
            f"Module step '{step.name}' requires a 'script' or 'script_file' "
            "argument in its 'with:' args."
        )
    local_path = Path(str(script_file)).expanduser()
    if not local_path.is_absolute():
        base_dir = workflow_dir or Path.cwd()
        local_path = (base_dir / local_path).resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"Script file not found: {local_path}")
    return local_path.read_text()

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

def _invoke_kwargs(_func, _args):
    # Mirrors ofx.modules.api.invoke_api_callable: filter the step args to the
    # function signature so unrelated workflow inputs are ignored.
    _params = _inspect.signature(_func).parameters
    if any(_p.kind is _inspect.Parameter.VAR_KEYWORD for _p in _params.values()):
        return _func(**_args)
    _kwargs = {{}}
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

def _resolve_api_step_target(step: Step, *, workflow_dir: Path | None = None) -> str | None:
    """Return the ``ofx.api`` dotted path for an api-backed step, else None.

    Covers ``local.api.<path>`` specs and remote manifest entries declared
    with an ``api:`` key (which may ship no ``.py`` files at all).
    """
    from ofx.modules.refs import API_KIND, REMOTE_KIND, parse_module_ref
    from ofx.modules.remote import ensure_remote_module

    module = getattr(step, "module", None) or ""
    ref = parse_module_ref(module_base_name(module))
    if ref.kind == API_KIND:
        return ref.api_path
    if ref.kind == REMOTE_KIND:
        entry = ensure_remote_module(ref, workflow_dir=workflow_dir)
        return entry.api_path
    return None


def _resolve_udf_target(
    step: Step, *, workflow_dir: Path | None = None
) -> tuple[Path, str]:
    """Resolve a UDF-like ``module:`` step to ``(file_path, function)``.

    Handles UDF file specs (``<file>.py[::<func>]``), workflow-local named
    modules (``local.<name>[::<func>]``) and remote GitHub modules
    (``<owner>.<repo>.<module>[@<ref>][::<func>]``), which are fetched into
    the local module cache on first use.

    Raises:
        ValueError: If the step is an ``ofx.api`` module (``local.api.*`` or a
            remote ``api:`` manifest entry), which has no UDF file.
    """
    # Imported lazily: ofx.modules.udf transitively pulls in ofx.runner,
    # which imports this module — an eager import would cycle.
    from ofx.modules.refs import (
        LOCAL_NAMED_KIND,
        REMOTE_KIND,
        parse_module_ref,
    )
    from ofx.modules.udf import DEFAULT_UDF_FUNCTION, split_udf_spec

    module = getattr(step, "module", None) or ""
    if not is_udf_module_step(step):
        raise ValueError(
            f"Step '{step.name}' is not a UDF module step: {module!r}"
        )
    ref = parse_module_ref(module)
    if ref.kind == REMOTE_KIND:
        from ofx.modules.remote import ensure_remote_module

        entry = ensure_remote_module(ref, workflow_dir=workflow_dir)
        if entry.api_path is not None:
            raise ValueError(
                f"Step '{step.name}' resolves to an 'api:' module "
                f"('ofx.api.{entry.api_path}') and has no UDF file "
                f"(spec {module!r})"
            )
        return entry.file, entry.function
    if ref.kind == LOCAL_NAMED_KIND:
        from ofx.modules.registry import LOCAL_MODULES_SUBDIR

        root = workflow_dir if workflow_dir is not None else Path.cwd()
        path = root / LOCAL_MODULES_SUBDIR / f"{ref.name}.py"
        return path, ref.function or DEFAULT_UDF_FUNCTION
    _path, function = split_udf_spec(module)
    from ofx.modules.udf import resolve_udf_path

    return resolve_udf_path(module, workflow_dir), function


def _resolve_udf_source(step: Step, *, workflow_dir: Path | None = None) -> str:
    """Return the resolved UDF/module file text for a ``module:`` UDF step."""
    module = getattr(step, "module", None) or ""
    resolved, _function = _resolve_udf_target(step, workflow_dir=workflow_dir)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"UDF module file not found: '{resolved}' (from spec {module!r})"
        )
    return resolved.read_text(encoding="utf-8")

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
    api_path = _resolve_api_step_target(step, workflow_dir=workflow_dir)
    if api_path is not None:
        return _build_api_udf_step_source(
            api_path,
            inputs_json=inputs_json,
            secrets_json=secrets_json,
        )
    _path, function = _resolve_udf_target(step, workflow_dir=workflow_dir)
    source = _resolve_udf_source(step, workflow_dir=workflow_dir)
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
    )

def parse_module_outputs_sentinel(stdout: str) -> tuple[str, dict[str, Any]]:
    """Parse a UDF wrapper's ``__OFX_MODULE_OUTPUTS__`` sentinel line.

    The sentinel is the last line printed on stdout:
    ``__OFX_MODULE_OUTPUTS__<base64-json>``. Returns ``(cleaned_stdout,
    outputs)``. When the sentinel is absent or cannot be parsed, the original
    stdout is returned with an empty outputs dict (raw stdout is preserved).
    """
    index = stdout.rfind(_MODULE_OUTPUTS_SENTINEL)
    if index == -1:
        return stdout, {}
    line_start = stdout.rfind("\n", 0, index) + 1
    line_end = stdout.find("\n", index)
    if line_end == -1:
        line_end = len(stdout)
    encoded = stdout[line_start:line_end][len(_MODULE_OUTPUTS_SENTINEL):].strip()
    if not encoded:
        return stdout, {}
    try:
        outputs = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except ValueError:
        return stdout, {}
    if not isinstance(outputs, dict):
        return stdout, {}
    cleaned = stdout[:line_start] + stdout[line_end + 1:]
    return cleaned, outputs

@lru_cache(maxsize=128)
def build_python_payload(
    source: str,
    *,
    opsec_mode: bool = False,
    obfuscate_sources: bool = False,
    extra_modules: tuple[str, ...] | None = None,
) -> str:
    """Return bundled payload (optionally obfuscated) for remote execution.

    *extra_modules* is a hashable tuple of ``ofx.api`` module names to
    force-include in the bundle. UDF wrappers use it because their
    ``ofx.api`` imports live inside an embedded string literal that the
    bundle's AST analyzer cannot see.
    """
    result = build_bundle(
        source,
        extra_modules=list(extra_modules) if extra_modules else None,
        obfuscate_sources=obfuscate_sources,
    )
    if opsec_mode:
        return obfuscate_bootstrap(result.bootstrap)
    return result.bootstrap

def build_python_step_payload(
    step: Step,
    *,
    workflow_dir: Path | None = None,
    opsec_mode: bool = False,
    obfuscate_sources: bool = False,
) -> str:
    """Resolve a Python-backed step and build its bundled execution payload."""
    source = resolve_python_step_source(step, workflow_dir=workflow_dir)
    return build_python_payload(
        source,
        opsec_mode=opsec_mode,
        obfuscate_sources=obfuscate_sources,
    )

def build_module_step_payload(
    step: Step,
    *,
    workflow_dir: Path | None = None,
    inputs: dict[str, Any] | None = None,
    secrets: dict[str, Any] | None = None,
    opsec_mode: bool = False,
    obfuscate_sources: bool = False,
) -> str:
    """Build the bundled execution payload for a remote ``module:`` step.

    Python steps bundle their resolved source directly; UDF steps are
    rendered into a wrapper source (see :func:`build_udf_step_source`) and
    run through the same payload path. A UDF file's ``ofx.api`` imports are
    invisible to the bundle analyzer (embedded as a string literal), so they
    are detected on the raw UDF source and force-included via
    ``extra_modules``. ``ofx.api``-backed steps need no such hint: their
    wrapper carries a real ``from ofx.api.<path> import <func>`` statement,
    which the analyzer detects in the generated source.
    """
    if is_python_module_step(step):
        return build_python_step_payload(
            step,
            workflow_dir=workflow_dir,
            opsec_mode=opsec_mode,
            obfuscate_sources=obfuscate_sources,
        )
    if is_udf_module_step(step):
        source = build_udf_step_source(
            step,
            workflow_dir=workflow_dir,
            inputs=inputs,
            secrets=secrets,
        )
        extra_modules: tuple[str, ...] = ()
        if _resolve_api_step_target(step, workflow_dir=workflow_dir) is None:
            extra_modules = tuple(
                sorted(
                    detect_ofx_imports(
                        _resolve_udf_source(step, workflow_dir=workflow_dir)
                    )
                )
            )
        return build_python_payload(
            source,
            extra_modules=extra_modules,
            opsec_mode=opsec_mode,
            obfuscate_sources=obfuscate_sources,
        )
    raise ValueError(
        f"Step '{step.name}' is not a supported remote module step: "
        f"{getattr(step, 'module', None)!r}"
    )
