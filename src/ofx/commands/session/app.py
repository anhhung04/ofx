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
from datetime import UTC
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from ofx.commands.ui_helpers import print_error, print_info, print_success
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "session"
HELP = "Manage detached job sessions (local & cloud)"


# ======================================================================
# Helpers
# ======================================================================


def _run_session_op(
    session_id: str,
    op_name: str,
    coro,
    *,
    error_title: str = "Operation failed",
    error_msg: str = "",
    extra_exc: tuple[type[Exception], ...] = (),
) -> Any:
    """Run an async SessionManager operation with standard error handling."""
    from ofx.cloud.sessions import SessionManager

    mgr = SessionManager()
    try:
        return asyncio.run(coro(mgr))
    except FileNotFoundError as exc:
        print_error("Session not found", f"Session '{session_id}' not found.")
        raise typer.Exit(code=1) from exc
    except (*extra_exc,) as exc:
        print_error(error_title, error_msg or f"{op_name} failed.", details=str(exc))
        raise typer.Exit(code=1) from exc


def _session_detail_table(session) -> Table:
    """Build a key-value detail table for a session."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    rows: list[tuple[str, str]] = [
        ("Session ID", f"[cyan]{session.id}[/cyan]"),
        ("Name", session.name),
    ]
    if session.project:
        rows.append(("Project", session.project))
    rows.append(("Target", session.target.value))
    rows.append(("Status", f"[{_status_style(session.status.value)}]{session.status.value}[/{_status_style(session.status.value)}]"))
    rows.append(("Workflow", session.workflow_file))
    rows.append(("Job", session.job_id))
    if session.remote_pid:
        rows.append(("PID", str(session.remote_pid)))
    if session.instance_ip:
        rows.append(("IP", session.instance_ip))
    if getattr(session, "cloud_provider", None):
        rows.append(("Provider", session.cloud_provider))
    if getattr(session, "started_at", None):
        rows.append(("Started", str(session.started_at)))
    if getattr(session, "finished_at", None):
        rows.append(("Finished", str(session.finished_at)))
    if hasattr(session, "age_display"):
        rows.append(("Age", session.age_display()))
    if getattr(session, "encrypted", False):
        rows.append(("Encrypted", f"[green]Yes[/green] → {session.encrypted_file}"))
    if getattr(session, "results_path", None):
        rows.append(("Results", session.results_path))
    if getattr(session, "error", None):
        rows.append(("Error", f"[red]{session.error}[/red]"))

    for key, val in rows:
        table.add_row(key, val)
    return table


def _status_style(status: str) -> str:
    """Rich markup style for a session status."""
    return {
        "provisioning": "yellow", "uploading": "yellow", "running": "bold cyan",
        "completed": "green", "failed": "red", "canceled": "dim yellow",
        "fetched": "bold green", "encrypted": "bold magenta", "destroyed": "dim red",
    }.get(status, "white")


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
    inputs: Annotated[list[str] | None, typer.Option("--input", "-i", help="Input key=value pairs")] = None,
):
    """Submit a workflow as a detached session."""
    console = get_console()
    from ofx.cloud.sessions import SessionManager, SessionTarget
    from ofx.commands import get_cli_env_vars, get_cli_project
    from ofx.utils.args import parse_key_value_pairs

    parsed_inputs: dict = parse_key_value_pairs(inputs or [])
    parsed_env: dict = get_cli_env_vars()

    session_project = get_cli_project()
    if not session_project:
        from ofx.commands.project.project_manager import ProjectManager
        active_path = ProjectManager.get_active_path()
        if active_path:
            session_project = active_path.name

    if cloud and local:
        print_error("Invalid options", "Cannot use both --local and --cloud.")
        raise typer.Exit(code=1)

    target = SessionTarget.CLOUD if cloud else SessionTarget.LOCAL
    mgr = SessionManager()

    try:
        session = asyncio.run(mgr.submit(
            workflow, job_id=job, target=target, cloud_profile=cloud,
            inputs=parsed_inputs, name=name, env=parsed_env, project=session_project,
        ))
    except Exception as exc:
        print_error("Submit failed", "Session submit failed.", details=str(exc))
        raise typer.Exit(code=1) from exc

    print_success("Session submitted", "Session submitted successfully.", details={
        "Session ID": session.id, "Name": session.name,
        "Target": session.target.value, "Status": session.status.value,
        "Workflow": session.workflow_file, "Job": session.job_id,
        **({"Project": session.project} if session.project else {}),
    })
    console.print(_session_detail_table(session))
    print_info("Next steps", "Useful follow-up commands.", details={
        "Check status": f"ofx session status {session.id}",
        "View logs": f"ofx session logs {session.id}",
        "Fetch results": f"ofx session fetch {session.id}",
    })


# ======================================================================
# List
# ======================================================================


@app.command("list")
def session_list(
    status: Annotated[str, typer.Option("--status", "-s", help="Filter by status")] = "",
    target: Annotated[str, typer.Option("--target", "-t", help="Filter: local or cloud")] = "",
    project: Annotated[str, typer.Option("--project", help="Filter by project name")] = "",
):
    """List all sessions."""
    console = get_console()
    from ofx.cloud.sessions import SessionStore

    store = SessionStore()
    _status = None
    if status:
        from ofx.cloud.sessions.models import SessionStatus
        try:
            _status = SessionStatus(status)
        except ValueError as exc:
            console.print(f"[red]Unknown status: {status}[/red]")
            console.print(f"[dim]Valid: {', '.join(s.value for s in SessionStatus)}[/dim]")
            raise typer.Exit(code=1) from exc

    sessions = store.list_sessions(status=_status, target=target or None, project=project or None)
    if not sessions:
        print_info("Sessions", "No sessions found.")
        return

    table = Table(title="Sessions")
    for col, opts in [
        ("ID", {"style": "cyan", "no_wrap": True}), ("Name", {}), ("Project", {}),
        ("Target", {}), ("Status", {}), ("Workflow", {}), ("IP/Host", {}),
        ("PID", {}), ("Age", {"justify": "right"}),
    ]:
        table.add_column(col, **opts)

    for s in sessions:
        ss = _status_style(s.status.value)
        table.add_row(
            s.id, s.name or "-", s.project or "-", s.target.value,
            f"[{ss}]{s.status.value}[/{ss}]", s.workflow_file,
            s.instance_ip or "(local)", str(s.remote_pid) if s.remote_pid else "-",
            s.age_display(),
        )
    console.print(table)


# ======================================================================
# Status
# ======================================================================


@app.command("status")
def session_status(session_id: Annotated[str, typer.Argument(help="Session ID")]):
    """Check the status of a session (probes PID if running)."""
    console = get_console()
    session = _run_session_op(session_id, "status", lambda mgr: mgr.status(session_id))
    console.print(_session_detail_table(session))


# ======================================================================
# Logs
# ======================================================================


@app.command("logs")
def session_logs(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of lines")] = 50,
):
    """View session output log (tail last N lines)."""
    console = get_console()
    output = _run_session_op(session_id, "logs", lambda mgr: mgr.logs(session_id, tail=tail))
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
    output_dir = Path(output) if output else None
    result_path = _run_session_op(
        session_id, "fetch",
        lambda mgr: mgr.fetch(session_id, passphrase=passphrase, output_dir=output_dir),
        error_title="Fetch failed", error_msg="Failed to fetch session results.",
        extra_exc=(RuntimeError,),
    )
    msg = "Results fetched and encrypted." if passphrase else "Results fetched."
    print_success("Results", msg, details={"Path": str(result_path)})


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
    output_dir = Path(output) if output else None
    result_path = _run_session_op(
        session_id, "decrypt",
        lambda mgr: mgr.decrypt(session_id, passphrase=passphrase, output_dir=output_dir),
        error_title="Decrypt failed", error_msg="Failed to decrypt session results.",
        extra_exc=(RuntimeError, ValueError),
    )
    print_success("Results", "Results decrypted.", details={"Path": str(result_path)})


# ======================================================================
# Cancel
# ======================================================================


@app.command("cancel")
def session_cancel(session_id: Annotated[str, typer.Argument(help="Session ID")]):
    """Cancel a running session (kills the process)."""
    session = _run_session_op(session_id, "cancel", lambda mgr: mgr.cancel(session_id))
    print_info("Session updated", f"Session {session_id} → {session.status.value}")


# ======================================================================
# Destroy
# ======================================================================


@app.command("destroy")
def session_destroy(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Force destroy even if running")] = False,
):
    """Destroy a cloud session's VPS. For local, cleans up workspace."""
    session = _run_session_op(
        session_id, "destroy",
        lambda mgr: mgr.destroy(session_id, force=force),
        error_title="Destroy failed", error_msg="Failed to destroy session.",
        extra_exc=(RuntimeError,),
    )
    print_info("Session updated", f"Session {session_id} → {session.status.value}")


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
    console = get_console()
    from ofx.cloud.sessions import SessionStore
    from ofx.cloud.sessions.models import SessionStatus

    store = SessionStore()

    age_seconds = None
    if older_than:
        age_seconds = _parse_duration(older_than)
        if age_seconds is None:
            print_error("Invalid duration", f"Invalid duration: {older_than}", details="Examples: 7d, 24h, 30m, 3600s")
            raise typer.Exit(code=1)

    statuses = []
    for s in status.split(","):
        s = s.strip()
        if s:
            try:
                statuses.append(SessionStatus(s))
            except ValueError as e:
                print_error("Invalid status", f"Unknown status: {s}")
                raise typer.Exit(code=1) from e

    all_sessions = store.list_sessions()
    matching = []
    for sess in all_sessions:
        if statuses and sess.status not in statuses:
            continue
        if age_seconds:
            from datetime import datetime
            age = (datetime.now(UTC) - sess.started_at).total_seconds()
            if age < age_seconds:
                continue
        matching.append(sess)

    if not matching:
        print_info("Sessions", "No sessions match the criteria.")
        return

    console.print(f"[yellow]Will remove {len(matching)} session(s):[/yellow]")
    for sess in matching:
        console.print(f"  {sess.id}  {sess.name or '-'}  {sess.status.value}  {sess.age_display()}")

    if not yes:
        if not typer.confirm("Proceed?"):
            print_info("Clean", "Aborted.")
            return

    removed = store.clean(older_than_seconds=age_seconds, statuses=statuses or None)
    print_success("Clean", f"Removed {removed} session(s).")
