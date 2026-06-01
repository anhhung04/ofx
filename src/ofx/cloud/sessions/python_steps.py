"""Shared helpers for Python-backed detached session steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.cloud.script_runtime import build_python_step_payload, is_python_step_run_type


def step_bundle_filename(step_index: int) -> str:
    """Return deterministic staged filename for Python step bundles."""
    return f".ofx_step_{step_index}.py"


def iter_python_step_bundles(
    steps: list[Any],
    *,
    workflow_dir: Path | None = None,
):
    """Yield staged bundle metadata for Python-backed workflow steps."""
    for idx, step in enumerate(steps):
        if not is_python_step_run_type(step.get_run_type()):
            continue
        yield idx, step_bundle_filename(idx), build_python_step_payload(
            step,
            workflow_dir=workflow_dir,
            opsec_mode=True,
            obfuscate_sources=True,
        )


__all__ = [
    "iter_python_step_bundles",
    "step_bundle_filename",
]
