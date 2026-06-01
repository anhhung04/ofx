"""Step output handling utilities."""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ofx.runner.metadata import ModelContext
from ofx.runner.step_descriptors import step_source_kind_and_value
from ofx.settings import settings

_OUTPUT_FLAG_LINES: tuple[tuple[str, str], ...] = (
    ("binary_output", "[BINARY OUTPUT]"),
    ("output_truncated", "[OUTPUT TRUNCATED]"),
    ("stderr_truncated", "[STDERR TRUNCATED]"),
)


def log_output(
    log_fn: Callable[[str], None],
    stream: str,
    content: str,
    *,
    max_lines: int | None = None,
) -> None:
    """Log a stdout/stderr stream, truncating if it exceeds *max_lines*."""
    if not content or not isinstance(content, str):
        return

    limit = max_lines if max_lines is not None else settings.max_display_lines
    lines = content.splitlines()

    if len(lines) > limit:
        head = "\n".join(lines[:limit])
        omitted = len(lines) - limit
        display = f"{head}\n... [{omitted} more lines - full output saved to logs]"
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
    """Persist full stdout to a log file under *output_path/logs/*."""
    if not output_path:
        return None

    model_context = ModelContext.from_model(step_model)
    step_name = (model_context.name or f"step_{model_context.step_index or 0}").replace(
        " ", "-"
    )
    log_path = Path(output_path) / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    out_file = log_path / f"stdout_{job_id}_{step_name}.log"

    output_flags = outputs or {}
    kind, value = step_source_kind_and_value(step_model)
    if kind == "script":
        encoded = base64.b64encode(str(value).encode()).decode()
        header = [f">> script (base64): {encoded}"]
    elif kind == "command":
        header = [f">> command: {value}"]
    elif kind == "workflow":
        header = [f">> workflow: {value}"]
    elif kind == "script_file":
        header = [f">> script_file: {value}"]
    elif kind == "task":
        header = [f">> task: {value}"]
    else:
        header = [">> unknown step type"]
    header.extend(
        line
        for flag, line in _OUTPUT_FLAG_LINES
        if output_flags.get(flag)
    )
    header.append(">>===<<")
    out_file.write_text("\n".join(header) + "\n" + stdout)

    if log_fn:
        log_fn(f"Saved output to {out_file}")

    return out_file


__all__ = ["log_output", "save_output_file"]
