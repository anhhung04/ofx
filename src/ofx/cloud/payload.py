"""Bundled payload building and sentinel parsing for remote module steps."""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ofx.api.bundle import build_bundle
from ofx.api.bundle.analyzer import detect_ofx_imports
from ofx.api.bundle.obfuscator import obfuscate_bootstrap
from ofx.cloud.module_kind import is_python_module_step, is_udf_module_step
from ofx.cloud.module_source import (
    resolve_api_step_target,
    resolve_python_step_source,
    resolve_udf_source,
)
from ofx.cloud.udf_wrapper import build_udf_step_source
from ofx.models.step import Step

MODULE_OUTPUTS_SENTINEL = "__OFX_MODULE_OUTPUTS__"

# Task completion markers: emitted by generated session scripts
# (sessions/script_builder.py) and scanned from session logs by the status
# poller (sessions/status.py). Defined once here so both sides stay in sync.
TASK_OK_MARKER = "__TASK_OK__"
TASK_ERR_MARKER = "__TASK_ERR__"


def parse_module_outputs_sentinel(stdout: str) -> tuple[str, dict[str, Any]]:
    """Parse a UDF wrapper's ``__OFX_MODULE_OUTPUTS__`` sentinel line.

    The sentinel is the last line printed on stdout:
    ``__OFX_MODULE_OUTPUTS__<base64-json>``. Returns ``(cleaned_stdout,
    outputs)``. When the sentinel is absent or cannot be parsed, the original
    stdout is returned with an empty outputs dict (raw stdout is preserved).
    """
    index = stdout.rfind(MODULE_OUTPUTS_SENTINEL)
    if index == -1:
        return stdout, {}
    line_start = stdout.rfind("\n", 0, index) + 1
    line_end = stdout.find("\n", index)
    if line_end == -1:
        line_end = len(stdout)
    encoded = stdout[line_start:line_end][len(MODULE_OUTPUTS_SENTINEL):].strip()
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
        if resolve_api_step_target(step, workflow_dir=workflow_dir) is None:
            extra_modules = tuple(
                sorted(
                    detect_ofx_imports(
                        resolve_udf_source(step, workflow_dir=workflow_dir)
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


__all__ = [
    "MODULE_OUTPUTS_SENTINEL",
    "TASK_ERR_MARKER",
    "TASK_OK_MARKER",
    "build_module_step_payload",
    "build_python_payload",
    "build_python_step_payload",
    "parse_module_outputs_sentinel",
]
