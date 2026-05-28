"""Shared helpers for Python-backed detached session steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.cloud.script_runtime import is_python_step_run_type


def step_bundle_filename(step_index: int) -> str:
    """Return deterministic staged filename for Python step bundles."""
    return f".ofx_step_{step_index}.py"


def build_step_bundle_source(step: Any, *, workflow_dir: Path | None = None) -> str:
    """Build bundled Python bootstrap source for `script`/`script_file` steps."""
    from ofx.cloud.script_runtime import build_python_step_payload

    return build_python_step_payload(
        step,
        workflow_dir=workflow_dir,
        opsec_mode=True,
        obfuscate_sources=True,
    )


def iter_python_steps(steps: list[Any]):
    """Yield `(index, step)` pairs for staged Python-backed workflow steps."""
    for idx, step in enumerate(steps):
        if is_python_step_run_type(step.get_run_type()):
            yield idx, step


__all__ = [
    "build_step_bundle_source",
    "iter_python_steps",
    "step_bundle_filename",
]
