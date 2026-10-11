"""Source resolution for remote module steps.

Resolves a step's ``module:`` reference to the Python source (or to the
``ofx.api`` dotted path) that has to be bundled for remote execution.
"""

from __future__ import annotations

from pathlib import Path

from ofx.cloud.module_kind import (
    is_python_module_step,
    is_udf_module_step,
    module_base_name,
)
from ofx.models.step import RunType, Step
from ofx.modules.base import DEFAULT_MODULE_FUNCTION, PYTHON_MODULE_REQUIRES_SCRIPT


def resolve_python_step_source(
    step: Step, *, workflow_dir: Path | None = None
) -> str:
    """Resolve Python source for a ``module: python`` step.

    The inline script is taken from the step's ``with:`` args
    (``run_with["script"]``); a ``script_file`` arg is read and returned
    when no inline script is given.
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
            f"Module step '{step.name}': {PYTHON_MODULE_REQUIRES_SCRIPT} "
            "(add a 'script' or 'script_file' entry to the step's 'with:' args)."
        )
    local_path = Path(str(script_file)).expanduser()
    if not local_path.is_absolute():
        base_dir = workflow_dir or Path.cwd()
        local_path = (base_dir / local_path).resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"Script file not found: {local_path}")
    return local_path.read_text()


def resolve_api_step_target(
    step: Step, *, workflow_dir: Path | None = None
) -> str | None:
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


def resolve_udf_target(
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
    from ofx.modules.udf import (
        resolve_local_named_path,
        split_udf_spec,
    )

    module = getattr(step, "module", None) or ""
    if not is_udf_module_step(step):
        raise ValueError(f"Step '{step.name}' is not a UDF module step: {module!r}")
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
        if entry.file is None:  # defensive: non-api entries always have a file
            raise ValueError(
                f"Step '{step.name}' remote module '{module!r}' resolved "
                "without an entry file"
            )
        return entry.file, entry.function
    if ref.kind == LOCAL_NAMED_KIND:
        path = resolve_local_named_path(workflow_dir, ref.name or "")
        return path, ref.function or DEFAULT_MODULE_FUNCTION
    _path, function = split_udf_spec(module)
    from ofx.modules.udf import resolve_udf_path

    return resolve_udf_path(module, workflow_dir), function


def resolve_udf_source(step: Step, *, workflow_dir: Path | None = None) -> str:
    """Return the resolved UDF/module file text for a ``module:`` UDF step."""
    module = getattr(step, "module", None) or ""
    resolved, _function = resolve_udf_target(step, workflow_dir=workflow_dir)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"UDF module file not found: '{resolved}' (from spec {module!r})"
        )
    return resolved.read_text(encoding="utf-8")


__all__ = [
    "resolve_api_step_target",
    "resolve_python_step_source",
    "resolve_udf_source",
    "resolve_udf_target",
]
