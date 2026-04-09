"""Command timeline logger — appends OFX step executions to oops-logger CSV.

Writes entries to the oops-logger engagement CSV at
``$OOPS_LOG_DIR/$OOPS_ENGAGEMENT.csv`` (default ``~/.oops/logs/default.csv``).
When a project is active, the engagement name defaults to the project name
so that OFX workflow commands appear alongside shell commands in the same
engagement timeline.

CSV format (matches oops-logger):
  title, command, tool, event_time, source_host, target_address, tags
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(f"{settings.app_branding}.timeline")

# oops-logger CSV header (must match oops-logger.zsh)
_OOPS_HEADER = "title,command,tool,event_time,source_host,target_address,tags"

# ── Target extraction (best-effort, mirrors oops-logger) ──────────────────

_IP_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)")
_URL_RE = re.compile(r"https?://([^\s/]+)")
_FLAG_TARGET_RE = re.compile(
    r"(?:-h|--host|--url|--target|-t|-u|-d)\s+(\S+)"
)


def detect_target(command: str) -> str:
    """Extract the most likely target (IP, hostname, URL) from a command."""
    m = _FLAG_TARGET_RE.search(command)
    if m:
        target = m.group(1).strip("'\"")
        target = re.sub(r"^https?://", "", target)
        return target.split("/")[0].split(":")[0]

    m = _URL_RE.search(command)
    if m:
        return m.group(1).split(":")[0]

    for m in _IP_RE.finditer(command):
        ip = m.group(1)
        if not ip.startswith(("127.", "0.0.")):
            return ip

    return ""


def _hostname() -> str:
    try:
        return socket.gethostname().split(".")[0]
    except Exception:
        return "unknown"


def _csv_row(values: list[str]) -> str:
    """Produce a single CSV row string (handles quoting/escaping)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(values)
    return buf.getvalue()


def _resolve_oops_csv(project_name: str) -> Path | None:
    """Resolve the oops-logger CSV file path for the current engagement.

    Priority:
      1. ``$OOPS_LOG_FILE`` — explicit override
      2. ``$OOPS_LOG_DIR / $OOPS_ENGAGEMENT.csv``
      3. ``$OOPS_LOG_DIR / <project_name>.csv`` (if project is active)
      4. ``~/.oops/logs/default.csv`` (fallback)
    """
    log_file = os.environ.get("OOPS_LOG_FILE")
    if log_file:
        return Path(log_file)

    log_dir = Path(os.environ.get("OOPS_LOG_DIR", "~/.oops/logs")).expanduser()
    engagement = os.environ.get("OOPS_ENGAGEMENT") or project_name or "default"
    return log_dir / f"{engagement}.csv"


def _ensure_csv(path: Path) -> None:
    """Create the CSV file with oops-logger header if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(_OOPS_HEADER + "\n")


def _format_duration(ms: int | None) -> str:
    if ms is None:
        return ""
    secs = ms / 1000
    if secs >= 3600:
        return f"{secs / 3600:.1f}h"
    if secs >= 60:
        return f"{secs / 60:.1f}m"
    return f"{secs:.1f}s"


# ── Public API ────────────────────────────────────────────────────────────


def log_step(
    *,
    ctx_vars: dict[str, Any],
    output_path: Path | None,
    step_name: str,
    command: str,
    tool: str,
    target: str,
    status: str,
    duration_ms: int | None,
    exit_code: int | str | None = None,
    tags: str = "",
) -> None:
    """Append a step execution record to the oops-logger engagement CSV.

    Uses the project name as engagement when available, falls back to
    ``$OOPS_ENGAGEMENT`` or ``"default"``.
    """
    project_name = ctx_vars.get("project_name", "")
    csv_path = _resolve_oops_csv(project_name)
    if csv_path is None:
        return

    resolved_target = target or detect_target(command)

    # Build title matching oops-logger format: [tool] command_preview
    tool_name = tool or ""
    cmd_preview = command[:80] if command else step_name
    title = f"[{tool_name}] {cmd_preview}" if tool_name else cmd_preview

    # Build tags: ofx + duration + status + any extra
    tag_parts = [f"ofx;duration:{_format_duration(duration_ms)};status:{status}"]
    if exit_code is not None and exit_code != 0:
        tag_parts.append(f"exit:{exit_code}")
    if tags:
        tag_parts.append(tags)
    all_tags = ";".join(tag_parts)

    try:
        _ensure_csv(csv_path)

        row = _csv_row([
            title,
            command,
            tool_name,
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            _hostname(),
            resolved_target,
            all_tags,
        ])

        with open(csv_path, "a") as f:
            f.write(row)
    except Exception as e:
        logger.debug("Failed to write oops timeline entry: %s", e)
