"""Shared Python step runtime helpers for cloud runner and sessions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ofx.api.bundle import build_bundle
from ofx.api.bundle.obfuscator import obfuscate_bootstrap
from ofx.models.step import RunType, Step

PYTHON_STEP_RUN_TYPES: frozenset[RunType] = frozenset(
    {RunType.SCRIPT, RunType.SCRIPT_FILE}
)


def is_python_step_run_type(run_type: RunType) -> bool:
    """Return whether a run type is backed by staged Python source."""
    return run_type in PYTHON_STEP_RUN_TYPES


def resolve_python_step_source(step: Step, *, workflow_dir: Path | None = None) -> str:
    """Resolve Python source for ``script``/``script_file`` step types."""
    run_type = step.get_run_type()
    if not is_python_step_run_type(run_type):
        raise ValueError(
            f"Unsupported step run type for python source resolution: {run_type}"
        )

    if run_type == RunType.SCRIPT:
        return step.script or ""

    script_file = step.script_file or ""
    local_path = Path(script_file).expanduser().with_suffix(".py")
    if not local_path.is_absolute():
        base_dir = workflow_dir or Path.cwd()
        local_path = (base_dir / local_path).resolve()
    if not local_path.is_file():
        raise FileNotFoundError(f"Script file not found: {local_path}")
    return local_path.read_text()


@lru_cache(maxsize=128)
def build_python_payload(
    source: str,
    *,
    opsec_mode: bool = False,
    obfuscate_sources: bool = False,
) -> str:
    """Return bundled payload (optionally obfuscated) for remote execution."""
    result = build_bundle(source, obfuscate_sources=obfuscate_sources)
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
