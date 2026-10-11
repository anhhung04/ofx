"""Shared helpers for module-backed detached session steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ofx.cloud.module_kind import is_python_module_step, is_udf_module_step
from ofx.cloud.payload import build_module_step_payload


def step_bundle_filename(step_index: int) -> str:
    """Return deterministic staged filename for module step bundles."""
    return f".ofx_step_{step_index}.py"

def iter_python_step_bundles(
    steps: list[Any],
    *,
    workflow_dir: Path | None = None,
):
    """Yield staged bundle metadata for module-backed workflow steps.

    Includes builtin python steps (source bundled directly) and UDF steps
    (wrapper source bundled through the same payload path). Shell steps are
    skipped — they run their ``with: {cmd: ...}`` command directly.
    """
    for idx, step in enumerate(steps):
        if not (is_python_module_step(step) or is_udf_module_step(step)):
            continue
        yield idx, step_bundle_filename(idx), build_module_step_payload(
            step,
            workflow_dir=workflow_dir,
            inputs=dict(step.run_with or {}),
            opsec_mode=True,
            obfuscate_sources=True,
        )

__all__ = [
    "iter_python_step_bundles",
    "step_bundle_filename",
]
