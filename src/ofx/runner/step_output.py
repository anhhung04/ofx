"""Step output handling utilities."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ofx.runner.step_descriptors import step_output_header_line
from ofx.settings import settings


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

    log_path = Path(output_path) / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    step_name = (
        getattr(step_model, "name", None)
        or f"step_{getattr(step_model, 'step_index', 0)}"
    ).replace(" ", "-")
    out_file = log_path / f"stdout_{job_id}_{step_name}.log"

    header = _build_header(step_model, outputs or {})
    out_file.write_text("\n".join(header) + "\n" + stdout)

    if log_fn:
        log_fn(f"Saved output to {out_file}")

    return out_file


def save_runner_output_file(
    output_path: Path | None,
    job_id: str | None,
    step_model: Any,
    stdout: str,
    outputs: dict[str, Any] | None = None,
    *,
    log_fn: Callable[[str], None] | None = None,
    missing_output_path_message: str | None = None,
    warn_fn: Callable[[str], None] | None = None,
) -> Path | None:
    """Persist step output when the caller has enough context to do so."""
    if not output_path:
        if missing_output_path_message and warn_fn:
            warn_fn(missing_output_path_message)
        return None
    if not job_id:
        return None
    return save_output_file(
        output_path,
        job_id,
        step_model,
        stdout,
        outputs,
        log_fn=log_fn,
    )


def _build_header(step_model: Any, outputs: dict[str, Any]) -> list[str]:
    """Build the metadata header lines for a log file."""
    header: list[str] = [step_output_header_line(step_model)]

    if outputs.get("binary_output"):
        header.append("[BINARY OUTPUT]")
    if outputs.get("output_truncated"):
        header.append("[OUTPUT TRUNCATED]")
    if outputs.get("stderr_truncated"):
        header.append("[STDERR TRUNCATED]")

    header.append(">>===<<")
    return header


__all__ = ["log_output", "save_output_file", "save_runner_output_file"]
