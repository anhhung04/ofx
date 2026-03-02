"""Session management CLI — submit, list, status, logs, fetch, cancel, destroy.

Usage:
    ofx session submit <workflow> [--local|--cloud profile] [--input k=v]
    ofx session list
    ofx session status <id>
    ofx session logs <id> [--tail N]
    ofx session fetch <id> [--passphrase pw] [--output dir]
    ofx session decrypt <id> --passphrase pw [--output dir]
    ofx session cancel <id>
    ofx session destroy <id> [--force]
    ofx session clean [--older-than 7d] [--status completed,fetched]
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "session"
HELP = "Manage detached job sessions (local & cloud)"

console = get_console()


# ======================================================================
# Submit
# ======================================================================


@app.command("submit")
def session_submit(
    workflow: Annotated[str, typer.Argument(help="Workflow file name or path")],
    job: Annotated[str, typer.Option("--job", "-j", help="Job ID to run (default: first job)")] = "",
    local: Annotated[bool, typer.Option("--local", "-l", help="Run as local background process")] = False,
    cloud: Annotated[str, typer.Option("--cloud", "-c", help="Cloud profile to use")] = "",
    name: Annotated[str, typer.Option("--name", "-n", help="Session name/tag")] = "",
    inputs: Annotated[list[str], typer.Option("--input", "-i", help="Input key=value pairs")] = [],
    env_vars: Annotated[list[str], typer.Option("-e", "--env", help="Environment KEY=VAL")] = [],
):
    """Submit a workflow as a detached session.

    By default runs locally. Use --cloud <profile> for VPS execution.
    """
    from ofx.cloud.sessions import SessionManager, SessionTarget
    from ofx.utils.args import parse_key_value_pairs

    # Parse inputs
    parsed_inputs: dict = parse_key_value_pairs(inputs)

    # Parse env
    parsed_env: dict = {}
    for ev in env_vars:
        if "=" in ev:
            k, v = ev.split("=", 1)
            parsed_env[k] = v

    # Determine target
    if cloud and local:
        console.print("[red]Cannot use both --local and --cloud[/red]")
        raise typer.Exit(code=1)

    if cloud:
        target = SessionTarget.CLOUD
    else:
        target = SessionTarget.LOCAL

    mgr = SessionManager()

    try:
        session = asyncio.run(
            mgr.submit(
                workflow,
                job_id=job,
                target=target,
                cloud_profile=cloud,
                inputs=parsed_inputs,
                name=name,
                env=parsed_env,
            )
        )
    except Exception as exc:
        console.print(f"[red]Submit failed:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print()
    console.print(f"[green]Session submitted successfully[/green]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value", style="cyan")
    table.add_row("Session ID", session.id)
    table.add_row("Name", session.name)
    table.add_row("Target", session.target.value)
    table.add_row("Status", session.status.value)
    table.add_row("Workflow", session.workflow_file)
    table.add_row("Job", session.job_id)
    if session.remote_pid:
        table.add_row("PID", str(session.remote_pid))
    if session.instance_ip:
        table.add_row("IP", session.instance_ip)
    console.print(table)
    console.print()
    console.print(f"[dim]Check status:  ofx session status {session.id}[/dim]")
    console.print(f"[dim]View logs:     ofx session logs {session.id}[/dim]")
    console.print(f"[dim]Fetch results: ofx session fetch {session.id}[/dim]")


# ======================================================================
# List
# ======================================================================


@app.command("list")
def session_list(
    status: Annotated[str, typer.Option("--status", "-s", help="Filter by status")] = "",
    target: Annotated[str, typer.Option("--target", "-t", help="Filter: local or cloud")] = "",
):
    """List all sessions."""
    from ofx.cloud.sessions import SessionStore

    store = SessionStore()
    _status = None
    if status:
        from ofx.cloud.sessions.models import SessionStatus

        try:
            _status = SessionStatus(status)
        except ValueError:
            console.print(f"[red]Unknown status: {status}[/red]")
            valid = ", ".join(s.value for s in SessionStatus)
            console.print(f"[dim]Valid: {valid}[/dim]")
            raise typer.Exit(code=1)

    sessions = store.list_sessions(status=_status, target=target or None)

    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Target")
    table.add_column("Status")
    table.add_column("Workflow")
    table.add_column("IP/Host")
    table.add_column("PID")
    table.add_column("Age", justify="right")

    for s in sessions:
        status_style = _status_style(s.status.value)
        table.add_row(
            s.id,
            s.name or "-",
            s.target.value,
            f"[{status_style}]{s.status.value}[/{status_style}]",
            s.workflow_file,
            s.instance_ip or "(local)",
            str(s.remote_pid) if s.remote_pid else "-",
            s.age_display(),
        )

    console.print(table)


# ======================================================================
# Status
# ======================================================================


@app.command("status")
def session_status(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
):
    """Check the status of a session (probes PID if running)."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()

    try:
        session = asyncio.run(mgr.status(session_id))
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)

    status_style = _status_style(session.status.value)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")
    table.add_row("Session ID", f"[cyan]{session.id}[/cyan]")
    table.add_row("Name", session.name)
    table.add_row("Target", session.target.value)
    table.add_row("Status", f"[{status_style}]{session.status.value}[/{status_style}]")
    table.add_row("Workflow", session.workflow_file)
    table.add_row("Job", session.job_id)
    if session.remote_pid:
        table.add_row("PID", str(session.remote_pid))
    if session.instance_ip:
        table.add_row("IP", session.instance_ip)
    if session.cloud_provider:
        table.add_row("Provider", session.cloud_provider)
    table.add_row("Started", str(session.started_at))
    if session.finished_at:
        table.add_row("Finished", str(session.finished_at))
    table.add_row("Age", session.age_display())
    if session.encrypted:
        table.add_row("Encrypted", f"[green]Yes[/green] → {session.encrypted_file}")
    if session.results_path:
        table.add_row("Results", session.results_path)
    if session.error:
        table.add_row("Error", f"[red]{session.error}[/red]")

    console.print(table)


# ======================================================================
# Logs
# ======================================================================


@app.command("logs")
def session_logs(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of lines")] = 50,
):
    """View session output log (tail last N lines)."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()

    try:
        output = asyncio.run(mgr.logs(session_id, tail=tail))
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)

    console.print(output)


# ======================================================================
# Fetch
# ======================================================================


@app.command("fetch")
def session_fetch(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    passphrase: Annotated[str, typer.Option("--passphrase", "-p", help="Encrypt results with this passphrase")] = "",
    output: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = "",
):
    """Fetch results from a completed session. Optionally encrypt with --passphrase."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()
    output_dir = Path(output) if output else None

    try:
        result_path = asyncio.run(
            mgr.fetch(session_id, passphrase=passphrase, output_dir=output_dir)
        )
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if passphrase:
        console.print(f"[green]Results encrypted →[/green] {result_path}")
    else:
        console.print(f"[green]Results fetched →[/green] {result_path}")


# ======================================================================
# Decrypt
# ======================================================================


@app.command("decrypt")
def session_decrypt(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    passphrase: Annotated[str, typer.Option("--passphrase", "-p", help="Decryption passphrase", prompt=True, hide_input=True)],
    output: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = "",
):
    """Decrypt previously encrypted session results."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()
    output_dir = Path(output) if output else None

    try:
        result_path = asyncio.run(
            mgr.decrypt(session_id, passphrase=passphrase, output_dir=output_dir)
        )
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)
    except (RuntimeError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Results decrypted →[/green] {result_path}")


# ======================================================================
# Cancel
# ======================================================================


@app.command("cancel")
def session_cancel(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
):
    """Cancel a running session (kills the process)."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()

    try:
        session = asyncio.run(mgr.cancel(session_id))
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)

    console.print(f"[yellow]Session {session_id} → {session.status.value}[/yellow]")


# ======================================================================
# Destroy
# ======================================================================


@app.command("destroy")
def session_destroy(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Force destroy even if running")] = False,
):
    """Destroy a cloud session's VPS. For local, cleans up workspace."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()

    try:
        session = asyncio.run(mgr.destroy(session_id, force=force))
    except FileNotFoundError:
        console.print(f"[red]Session '{session_id}' not found[/red]")
        raise typer.Exit(code=1)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[yellow]Session {session_id} → {session.status.value}[/yellow]")


# ======================================================================
# Clean
# ======================================================================


@app.command("clean")
def session_clean(
    older_than: Annotated[str, typer.Option("--older-than", help="Age threshold (e.g., 7d, 24h, 30m)")] = "",
    status: Annotated[str, typer.Option("--status", "-s", help="Comma-separated statuses to clean")] = "completed,fetched,encrypted,destroyed,canceled",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
):
    """Remove old session data from disk."""
    from ofx.cloud.sessions import SessionStore
    from ofx.cloud.sessions.models import SessionStatus

    store = SessionStore()

    # Parse age threshold
    age_seconds = None
    if older_than:
        age_seconds = _parse_duration(older_than)
        if age_seconds is None:
            console.print(f"[red]Invalid duration: {older_than}[/red]")
            console.print("[dim]Examples: 7d, 24h, 30m, 3600s[/dim]")
            raise typer.Exit(code=1)

    # Parse statuses
    statuses = []
    for s in status.split(","):
        s = s.strip()
        if s:
            try:
                statuses.append(SessionStatus(s))
            except ValueError:
                console.print(f"[red]Unknown status: {s}[/red]")
                raise typer.Exit(code=1)

    # Preview
    all_sessions = store.list_sessions()
    matching = []
    for sess in all_sessions:
        if statuses and sess.status not in statuses:
            continue
        if age_seconds:
            from datetime import datetime, timezone
            age = (datetime.now(timezone.utc) - sess.started_at).total_seconds()
            if age < age_seconds:
                continue
        matching.append(sess)

    if not matching:
        console.print("[dim]No sessions match the criteria.[/dim]")
        return

    console.print(f"[yellow]Will remove {len(matching)} session(s):[/yellow]")
    for sess in matching:
        console.print(f"  {sess.id}  {sess.name or '-'}  {sess.status.value}  {sess.age_display()}")

    if not yes:
        confirm = typer.confirm("Proceed?")
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            return

    removed = store.clean(older_than_seconds=age_seconds, statuses=statuses or None)
    console.print(f"[green]Removed {removed} session(s).[/green]")


# ======================================================================
# Helpers
# ======================================================================


def _status_style(status: str) -> str:
    """Rich markup style for a session status."""
    styles = {
        "provisioning": "yellow",
        "uploading": "yellow",
        "running": "bold cyan",
        "completed": "green",
        "failed": "red",
        "canceled": "dim yellow",
        "fetched": "bold green",
        "encrypted": "bold magenta",
        "destroyed": "dim red",
    }
    return styles.get(status, "white")


def _parse_duration(s: str) -> int | None:
    """Parse a human duration string like '7d', '24h', '30m', '3600s' into seconds."""
    s = s.strip().lower()
    if not s:
        return None
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if s[-1] in multipliers:
        try:
            return int(s[:-1]) * multipliers[s[-1]]
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        return None
