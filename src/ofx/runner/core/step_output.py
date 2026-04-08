"""Step output handling utilities.

Shared helpers for logging and persisting step output, used by both
``StepRunner`` (local) and ``CloudStepRunner`` (remote).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ofx.settings import settings


def log_output(
    log_fn: Callable[[str], None],
    stream: str,
    content: str,
    *,
    max_lines: int | None = None,
) -> None:
    """Log a stdout/stderr stream, truncating if it exceeds *max_lines*.

    Args:
        log_fn: Callable that accepts a single string message.
        stream: Label for the block (e.g. ``"stdout"`` or ``"stderr"``).
        content: The raw output text.
        max_lines: Override for ``settings.max_display_lines``.
    """
    if not content or not isinstance(content, str):
        return

    limit = max_lines if max_lines is not None else settings.max_display_lines
    lines = content.splitlines()

    if len(lines) > limit:
        head = "\n".join(lines[:limit])
        omitted = len(lines) - limit
        display = (
            f"{head}\n"
            f"... [{omitted} more lines — full output saved to logs]"
        )
    else:
        display = content

    log_fn(f"\n==={stream}===\n{display}\n===========")


def save_output_file(
    output_path: Path,
    job_id: str,
    step_model: Any,
    stdout: str,
    outputs: dict[str, Any] | None = None,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> Path | None:
    """Persist full stdout to a log file under *output_path/logs/*.

    Args:
        output_path: Base output directory (usually ``ctx.output_path``).
        job_id: Parent job identifier.
        step_model: The step model (used for header metadata).
        stdout: Full stdout text to save.
        outputs: Optional outputs dict for metadata flags.
        log_fn: Optional callable for info logging.

    Returns:
        The path to the saved file, or ``None`` if skipped.
    """
    if not output_path:
        return None

    log_path = Path(output_path) / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    step_name = (
        getattr(step_model, "name", None)
        or f"step_{getattr(step_model, 'step_index', 0)}"
    ).replace(" ", "-")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = log_path / f"stdout_{job_id}_{step_name}__{timestamp}.log"

    header = _build_header(step_model, outputs or {})
    out_file.write_text("\n".join(header) + "\n" + stdout)

    if log_fn:
        log_fn(f"Saved output to {out_file}")

    return out_file


def _build_header(step_model: Any, outputs: dict[str, Any]) -> list[str]:
    """Build the metadata header lines for a log file."""
    header: list[str] = []

    run_val = getattr(step_model, "run", None)
    uses_val = getattr(step_model, "uses", None)
    script_file_val = getattr(step_model, "script_file", None)
    script_val = getattr(step_model, "script", None)
    task_val = getattr(step_model, "task", None)

    if run_val:
        header.append(f">> command: {run_val}")
    elif uses_val:
        header.append(f">> workflow: {uses_val}")
    elif script_file_val:
        header.append(f">> script_file: {script_file_val}")
    elif script_val:
        header.append(
            f">> script (base64): {base64.b64encode(script_val.encode()).decode()}"
        )
    elif task_val:
        header.append(f">> task: {task_val}")
    else:
        header.append(">> unknown step type")

    if outputs.get("binary_output"):
        header.append("[BINARY OUTPUT]")
    if outputs.get("output_truncated"):
        header.append("[OUTPUT TRUNCATED]")
    if outputs.get("stderr_truncated"):
        header.append("[STDERR TRUNCATED]")

    header.append(">>===<<")
    return header
