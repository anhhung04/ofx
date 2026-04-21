"""CLI subcommands for managing durable checkpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from ofx.commands.ui_helpers import print_info, print_success, print_warning
from ofx.models.config import DurableRunConfig
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def _parse_age(age: str) -> float | None:
    """Parse a human-readable age string (e.g. '7d', '24h', '30m') to seconds."""
    if not age:
        return None
    age = age.strip().lower()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    suffix = age[-1]
    if suffix in multipliers:
        try:
            return float(age[:-1]) * multipliers[suffix]
        except ValueError:
            raise typer.BadParameter(f"Invalid age format: {age}") from None
    try:
        return float(age)
    except ValueError:
        raise typer.BadParameter(
            f"Invalid age format: {age}. Use a number with optional suffix: s, m, h, d, w"
        ) from None


def _resolve_output_path(output: str, project: str) -> Path:
    """Resolve the output directory for checkpoint operations.

    Priority: explicit output arg > --project flag > global -p flag > active project.
    """
    if output:
        return Path(output).expanduser()

    from ofx.commands import get_cli_project
    from ofx.commands.project.project_manager import ProjectManager

    resolved_project = project or get_cli_project()
    if not resolved_project:
        active_path = ProjectManager.get_active_path()
        if active_path:
            resolved_project = active_path.name

    if resolved_project:
        try:
            project_path = Path(ProjectManager.resolve_path(resolved_project))
            if project_path.is_dir():
                return project_path
        except Exception:
            pass

    raise typer.BadParameter(
        "No output directory specified and no active project found. "
        "Provide an output path or set an active project with 'ofx project active <name>'."
    )


@app.command("list")
def checkpoint_list(
    output: Annotated[
        str,
        typer.Argument(help="Output directory containing .durable/ checkpoint data. Auto-resolved from active project when omitted."),
    ] = "",
    project: Annotated[
        str,
        typer.Option("-p", "--project", help="Resolve output path from this project."),
    ] = "",
    status: Annotated[
        str,
        typer.Option("-s", "--status", help="Filter by status (comma-separated)."),
    ] = "",
    backend: Annotated[
        str,
        typer.Option("--backend", help="Durable backend: file or redis."),
    ] = "file",
):
    """List durable checkpoints in an output directory."""
    from ofx.runner.core.durable import list_checkpoints

    config = DurableRunConfig(enabled=True, backend=backend)
    path = _resolve_output_path(output, project)

    if not path.is_dir():
        print_warning("Not Found", f"Directory not found: {path}")
        raise typer.Exit(code=1)

    checkpoints = asyncio.run(list_checkpoints(path, config))

    if status:
        filter_statuses = {s.strip() for s in status.split(",")}
        checkpoints = [c for c in checkpoints if c.get("status") in filter_statuses]

    if not checkpoints:
        print_info("Checkpoints", "No checkpoints found.")
        return

    from rich.table import Table

    console = get_console()
    table = Table(title=f"Checkpoints ({len(checkpoints)})", show_lines=False, padding=(0, 1))
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Runner", style="dim")
    table.add_column("Started", style="dim")
    table.add_column("Duration", style="dim", justify="right")

    for cp in sorted(checkpoints, key=lambda c: c.get("started_at", "")):
        name = cp.get("name") or cp.get("checkpoint_id", "?")
        st = cp.get("status", "?")
        style = {"completed": "green", "failed": "red", "running": "yellow"}.get(st, "")
        runner_type = cp.get("runner_type", "")
        started = cp.get("started_at", "")[:19] if cp.get("started_at") else ""
        dur = cp.get("duration_ms")
        dur_str = f"{dur}ms" if dur is not None else ""

        table.add_row(str(name), f"[{style}]{st}[/]" if style else st, runner_type, started, dur_str)

    console.print(table)


@app.command("show")
def checkpoint_show(
    output: Annotated[
        str,
        typer.Argument(help="Output directory containing .durable/ checkpoint data. Auto-resolved from active project when omitted."),
    ] = "",
    project: Annotated[
        str,
        typer.Option("-p", "--project", help="Resolve output path from this project."),
    ] = "",
    checkpoint_id: Annotated[
        str,
        typer.Option("--id", help="Checkpoint ID to show details for."),
    ] = "",
    backend: Annotated[
        str,
        typer.Option("--backend", help="Durable backend: file or redis."),
    ] = "file",
):
    """Show details of a specific checkpoint or all checkpoints as JSON."""
    import json

    from ofx.runner.core.durable import get_checkpoint, list_checkpoints

    config = DurableRunConfig(enabled=True, backend=backend)
    path = _resolve_output_path(output, project)

    if not path.is_dir():
        print_warning("Not Found", f"Directory not found: {path}")
        raise typer.Exit(code=1)

    console = get_console()

    if checkpoint_id:
        cp = asyncio.run(get_checkpoint(path, config, checkpoint_id))
        if not cp:
            print_warning("Not Found", f"Checkpoint not found: {checkpoint_id}")
            raise typer.Exit(code=1)
        console.print_json(json.dumps(cp, default=str, indent=2))
    else:
        checkpoints = asyncio.run(list_checkpoints(path, config))
        if not checkpoints:
            print_info("Checkpoints", "No checkpoints found.")
            return
        console.print_json(json.dumps(checkpoints, default=str, indent=2))


@app.command("clean")
def checkpoint_clean(
    output: Annotated[
        str,
        typer.Argument(help="Output directory containing .durable/ checkpoint data. Auto-resolved from active project when omitted."),
    ] = "",
    project: Annotated[
        str,
        typer.Option("-p", "--project", help="Resolve output path from this project."),
    ] = "",
    status: Annotated[
        str,
        typer.Option("-s", "--status", help="Remove only checkpoints with these statuses (comma-separated)."),
    ] = "",
    older_than: Annotated[
        str,
        typer.Option("--older-than", help="Remove checkpoints older than this (e.g. 7d, 24h, 30m)."),
    ] = "",
    stale: Annotated[
        bool,
        typer.Option("--stale", help="Remove only stale (stuck in running) checkpoints."),
    ] = False,
    all_checkpoints: Annotated[
        bool,
        typer.Option("--all", help="Remove all checkpoints."),
    ] = False,
    backend: Annotated[
        str,
        typer.Option("--backend", help="Durable backend: file or redis."),
    ] = "file",
    yes: Annotated[
        bool,
        typer.Option("-y", "--yes", help="Skip confirmation prompt."),
    ] = False,
):
    """Clean durable checkpoints from an output directory."""
    from ofx.runner.core.durable import (
        clean_all_checkpoints,
        clean_checkpoints,
        clean_stale_checkpoints,
        list_checkpoints,
    )

    config = DurableRunConfig(enabled=True, backend=backend)
    path = _resolve_output_path(output, project)

    if not path.is_dir():
        print_warning("Not Found", f"Directory not found: {path}")
        raise typer.Exit(code=1)

    existing = asyncio.run(list_checkpoints(path, config))
    if not existing:
        print_info("Clean", "No checkpoints to clean.")
        return

    if all_checkpoints:
        if not yes:
            typer.confirm(f"Remove all {len(existing)} checkpoint(s)?", abort=True)
        count = asyncio.run(clean_all_checkpoints(path, config))
        print_success("Cleaned", f"Removed {count} checkpoint(s).")
        return

    if stale:
        count = asyncio.run(clean_stale_checkpoints(path, config))
        print_success("Cleaned", f"Removed {count} stale checkpoint(s).")
        return

    age_seconds = _parse_age(older_than)
    statuses: list[str] | None = [s.strip() for s in status.split(",") if s.strip()] or None

    if not statuses and age_seconds is None:
        print_warning("No Filter", "Specify --status, --older-than, --stale, or --all.")
        raise typer.Exit(code=1)

    count = asyncio.run(
        clean_checkpoints(path, config, status=statuses, older_than_seconds=age_seconds)
    )
    print_success("Cleaned", f"Removed {count} checkpoint(s).")
