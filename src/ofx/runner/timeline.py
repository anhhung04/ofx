"""Command log writer for OFX step executions."""

from __future__ import annotations

import json
import logging
import os
import re
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.settings import settings

logger = logging.getLogger(f"{settings.app_branding}.timeline")

_IP_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)")
_URL_RE = re.compile(r"https?://([^\s/]+)")
_FLAG_TARGET_RE = re.compile(r"(?:-h|--host|--url|--target|-t|-u|-d)\s+(\S+)")


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
        logger.debug("Failed to resolve hostname", exc_info=True)
        return "unknown"


_source_host_cache: str = ""


def _source_host() -> str:
    """Return ``hostname (public_ip)`` when an IP can be determined."""
    global _source_host_cache
    if _source_host_cache:
        return _source_host_cache

    host = os.environ.get("OFX_COMMAND_LOG_SOURCE_HOST") or _hostname()
    ip = os.environ.get("OFX_COMMAND_LOG_SOURCE_IP", "")

    if not ip:
        import urllib.request

        for url in (
            "https://ifconfig.me",
            "https://api.ipify.org",
            "https://icanhazip.com",
        ):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
                with urllib.request.urlopen(req, timeout=2) as resp:
                    candidate = resp.read().decode().strip()
                    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", candidate):
                        ip = candidate
                        break
            except Exception:
                logger.debug("Public IP lookup failed for %s", url, exc_info=True)
                continue

    if not ip:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(1)
                s.connect(("1.1.1.1", 80))
                ip = s.getsockname()[0]
        except Exception:
            logger.debug("Local IP detection via socket failed", exc_info=True)
            ip = ""

    if ip and ip != host:
        _source_host_cache = f"{host} ({ip})"
    else:
        _source_host_cache = host

    return _source_host_cache


def _resolve_command_log_path(ctx_vars: dict[str, Any]) -> Path:
    """Resolve the command log path, preferring the active project's logs dir."""
    log_file = os.environ.get("OFX_COMMAND_LOG_FILE")
    if log_file:
        return Path(log_file).expanduser()

    project_logs = ctx_vars.get("project_logs")
    if project_logs:
        return Path(str(project_logs)).expanduser() / "command_log.ndjson"

    project_path = ctx_vars.get("project_path")
    if project_path:
        return Path(str(project_path)).expanduser() / "logs" / "command_log.ndjson"

    log_dir = os.environ.get("OFX_COMMAND_LOG_DIR")
    if log_dir:
        name = ctx_vars.get("project_name") or os.environ.get("OFX_COMMAND_LOG_NAME") or "default"
        return Path(log_dir).expanduser() / f"{name}.ndjson"

    return Path("~/.ofx/logs/command/default.ndjson").expanduser()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _format_duration(ms: int | None) -> str:
    if ms is None:
        return ""
    secs = ms / 1000
    if secs >= 3600:
        return f"{secs / 3600:.1f}h"
    if secs >= 60:
        return f"{secs / 60:.1f}m"
    return f"{secs:.1f}s"


def _build_tags(*, status: str, duration: str, exit_code: int | str | None, tags: str) -> list[str]:
    parts = ["ofx"]
    if duration:
        parts.append(f"duration:{duration}")
    parts.append(f"status:{status}")
    if exit_code is not None and exit_code != 0:
        parts.append(f"exit:{exit_code}")
    if tags:
        parts.extend(tag for tag in tags.split(";") if tag)
    return parts


def log_step(
    *,
    ctx_vars: dict[str, Any],
    step_name: str,
    command: str,
    tool: str,
    target: str,
    status: str,
    duration_ms: int | None,
    exit_code: int | str | None = None,
    tags: str = "",
    source_host: str = "",
) -> None:
    """Append a structured step execution record to the command log."""
    log_path = _resolve_command_log_path(ctx_vars)
    resolved_target = target or detect_target(command)
    duration = _format_duration(duration_ms)
    record = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_name": ctx_vars.get("project_name", ""),
        "step_name": step_name,
        "command": command,
        "tool": tool or "",
        "target": resolved_target,
        "status": status,
        "duration_ms": duration_ms,
        "duration": duration,
        "exit_code": exit_code,
        "source_host": source_host or _source_host(),
        "tags": _build_tags(
            status=status,
            duration=duration,
            exit_code=exit_code,
            tags=tags,
        ),
    }

    try:
        _ensure_parent_dir(log_path)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception as exc:
        logger.debug("Failed to write command log entry: %s", exc)


__all__ = ["_format_duration", "_resolve_command_log_path", "detect_target", "log_step"]
