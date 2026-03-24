"""Run history tracking and display for OFX workflow executions."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ofx.settings import BASE_DATA_DIR, ensure_dir, settings

logger = logging.getLogger(f"{settings.app_branding}.history")

HISTORY_DIR = BASE_DATA_DIR / "history"
HISTORY_FILE = HISTORY_DIR / "runs.ndjson"
MAX_HISTORY_ENTRIES = 500


def save_run_record(
    *,
    run_id: str,
    workflow_name: str,
    status: str,
    error: str | None = None,
    inputs: dict[str, Any] | None = None,
    project: str = "",
    output_path: str = "",
    elapsed_seconds: float = 0.0,
    summary: dict[str, Any] | None = None,
) -> None:
    """Append a run record to the NDJSON history file."""
    record = {
        "run_id": run_id,
        "workflow": workflow_name,
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "project": project or "",
        "output_path": output_path,
    }
    if error:
        record["error"] = error[:200]
    if inputs:
        record["inputs"] = {k: str(v)[:100] for k, v in inputs.items()}
    if summary:
        record["total_jobs"] = summary.get("total_jobs", 0)
        record["failed_jobs"] = summary.get("failed_jobs", 0)
        record["total_steps"] = summary.get("total_steps", 0)
        record["failed_steps"] = summary.get("failed_steps", 0)

    try:
        ensure_dir(HISTORY_DIR)
        with open(HISTORY_FILE, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        logger.debug("Failed to save run history: %s", e)


def load_history(limit: int = 50, workflow: str = "", status: str = "") -> list[dict]:
    """Load run history records, newest first."""
    if not HISTORY_FILE.exists():
        return []

    records: list[dict] = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if workflow and workflow.lower() not in record.get("workflow", "").lower():
                        continue
                    if status and record.get("status", "").lower() != status.lower():
                        continue
                    records.append(record)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug("Failed to read run history: %s", e)
        return []

    # Newest first
    records.reverse()
    return records[:limit]


def clear_history() -> int:
    """Clear all run history. Returns number of records cleared."""
    if not HISTORY_FILE.exists():
        return 0
    try:
        count = sum(1 for line in open(HISTORY_FILE) if line.strip())
        HISTORY_FILE.unlink()
        return count
    except Exception:
        return 0


def prune_history(keep: int = MAX_HISTORY_ENTRIES) -> int:
    """Prune history to keep only the most recent N entries. Returns number pruned."""
    if not HISTORY_FILE.exists():
        return 0
    try:
        lines = [l for l in open(HISTORY_FILE) if l.strip()]
        if len(lines) <= keep:
            return 0
        pruned = len(lines) - keep
        with open(HISTORY_FILE, "w") as f:
            for line in lines[-keep:]:
                f.write(line if line.endswith("\n") else line + "\n")
        return pruned
    except Exception:
        return 0


def show_history(
    limit: int = 20,
    workflow: str = "",
    status: str = "",
    verbose: bool = False,
) -> None:
    """Display run history as a rich table."""
    from rich.table import Table

    from ofx.commands.ui_helpers import print_warning
    from ofx.settings import get_console

    console = get_console()
    records = load_history(limit=limit, workflow=workflow, status=status)

    if not records:
        if workflow or status:
            print_warning("No Runs Found", f"No runs match the filter (workflow={workflow!r}, status={status!r}).")
        else:
            print_warning("No Run History", "No workflow runs recorded yet. Run a workflow to start tracking.")
        return

    table = Table(title=f"Run History (last {len(records)})", show_lines=False, padding=(0, 1))
    table.add_column("Run ID", style="dim", max_width=12)
    table.add_column("Workflow", style="cyan bold")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right", style="white")
    table.add_column("Time", style="dim")
    if verbose:
        table.add_column("Project", style="yellow")
        table.add_column("Jobs", justify="right")
        table.add_column("Steps", justify="right")

    for rec in records:
        run_id = rec.get("run_id", "")[:8]
        wf_name = rec.get("workflow", "?")
        st = rec.get("status", "?")
        elapsed = rec.get("elapsed_seconds", 0)
        ts = rec.get("timestamp", "")

        # Status formatting
        if st == "completed":
            status_str = "[green]✓ OK[/green]"
        elif st == "failed":
            status_str = "[red]✗ FAIL[/red]"
        elif st == "canceled":
            status_str = "[yellow]⊘ CANCEL[/yellow]"
        else:
            status_str = f"[dim]{st}[/dim]"

        # Duration formatting
        if elapsed >= 3600:
            dur = f"{elapsed / 3600:.1f}h"
        elif elapsed >= 60:
            dur = f"{elapsed / 60:.1f}m"
        else:
            dur = f"{elapsed:.1f}s"

        # Time formatting (relative)
        time_str = _relative_time(ts)

        row = [run_id, wf_name, status_str, dur, time_str]
        if verbose:
            project = rec.get("project", "") or "-"
            total_jobs = rec.get("total_jobs", "")
            total_steps = rec.get("total_steps", "")
            failed_jobs = rec.get("failed_jobs", 0)
            failed_steps = rec.get("failed_steps", 0)
            jobs_str = str(total_jobs) if total_jobs else "-"
            if failed_jobs:
                jobs_str += f" [red]({failed_jobs} failed)[/red]"
            steps_str = str(total_steps) if total_steps else "-"
            if failed_steps:
                steps_str += f" [red]({failed_steps} failed)[/red]"
            row.extend([project, jobs_str, steps_str])

        table.add_row(*row)

    console.print(table)


def _relative_time(iso_ts: str) -> str:
    """Convert ISO timestamp to relative time string."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta = now - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        elif seconds < 604800:
            return f"{seconds // 86400}d ago"
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_ts[:16] if len(iso_ts) > 16 else iso_ts
