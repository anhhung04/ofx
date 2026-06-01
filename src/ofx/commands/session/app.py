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
    ofx session guard [--older-than 7d]
    ofx session bundle <id> [--output out.tar.gz]
"""

from __future__ import annotations

import asyncio
from datetime import UTC
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from ofx.commands.ui_helpers import (
    error_exit,
    print_info,
    print_success,
    session_status_style,
)
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "session"
HELP = "Manage detached workflow sessions (local & cloud)"

SessionManager = None
SessionStore = None
SessionStatus = None
SessionTarget = None
get_cli_env_vars = None
get_cli_project = None
parse_key_value_pairs = None
ProjectManager = None


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
    mgr = _get_session_manager_cls()()
    try:
        return asyncio.run(coro(mgr))
    except FileNotFoundError:
        error_exit("Session not found", f"Session '{session_id}' not found.")
    except (*extra_exc,) as exc:
        error_exit(error_title, error_msg or f"{op_name} failed.", details=str(exc))


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
    style = session_status_style(session.status.value)
    rows.append(("Status", f"[{style}]{session.status.value}[/{style}]"))
    rows.append(("Workflow", session.workflow_file))
    scope = session.job_id if session.job_id else "full-workflow"
    rows.append(("Execution scope", scope))
    if session.remote_pid:
        rows.append(("PID", str(session.remote_pid)))
    if session.instance_ip:
        rows.append(("IP", session.instance_ip))
    if getattr(session, "cloud_provider", None):
        rows.append(("Provider", session.cloud_provider))
    if session.target.value == "cloud":
        auto_destroy = "Yes" if getattr(session, "auto_destroy", True) else "No"
        rows.append(("Auto destroy", auto_destroy))
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



def _get_session_manager_cls():
    session_manager_cls = SessionManager
    if session_manager_cls is None:
        from ofx.cloud.sessions import SessionManager as session_manager_cls

    return session_manager_cls


def _get_session_store_cls():
    session_store_cls = SessionStore
    if session_store_cls is None:
        from ofx.cloud.sessions import SessionStore as session_store_cls

    return session_store_cls


def _get_session_status_cls():
    session_status_cls = SessionStatus
    if session_status_cls is None:
        from ofx.cloud.sessions.models import SessionStatus as session_status_cls

    return session_status_cls


def _get_session_store_and_status_deps():
    return _get_session_store_cls()(), _get_session_status_cls()


def _parse_age_seconds(value: str) -> int | None:
    raw = value.strip().lower()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if not raw:
        return None
    if raw[-1] in multipliers:
        try:
            return int(raw[:-1]) * multipliers[raw[-1]]
        except ValueError:
            return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_age_seconds_or_exit(value: str) -> int:
    age_seconds = _parse_age_seconds(value)
    if age_seconds is None:
        error_exit(
            "Invalid duration",
            f"Invalid duration: {value}",
            details="Examples: 7d, 24h, 30m, 3600s",
        )
    return age_seconds



def _get_session_submit_deps():
    key_value_parser = parse_key_value_pairs
    if key_value_parser is None:
        from ofx.utils.args import parse_key_value_pairs as key_value_parser

    cli_env_getter = get_cli_env_vars
    if cli_env_getter is None:
        from ofx.commands import get_cli_env_vars as cli_env_getter

    cli_project_getter = get_cli_project
    if cli_project_getter is None:
        from ofx.commands import get_cli_project as cli_project_getter

    session_target_cls = SessionTarget
    if session_target_cls is None:
        from ofx.cloud.sessions import SessionTarget as session_target_cls

    session_manager_cls = SessionManager
    if session_manager_cls is None:
        from ofx.cloud.sessions import SessionManager as session_manager_cls

    return (
        key_value_parser,
        cli_env_getter,
        cli_project_getter,
        session_target_cls,
        session_manager_cls,
    )


def _resolve_session_project(cli_project_getter) -> str:
    session_project = cli_project_getter()
    if session_project:
        return session_project

    project_manager_cls = ProjectManager
    if project_manager_cls is None:
        from ofx.commands.project.project_manager import ProjectManager as project_manager_cls

    active_path = project_manager_cls.get_active_path()
    return active_path.name if active_path else ""


def _print_session_update(session_id: str, session) -> None:
    print_info("Session updated", f"Session {session_id} → {session.status.value}")


def _print_success_path(title: str, message: str, path: Path) -> None:
    print_success(title, message, details={"Path": str(path)})

def _print_result_path(message: str, result_path: Path) -> None:
    _print_success_path("Results", message, result_path)


def _print_cleanup_result(title: str, message: str, removed: int) -> None:
    print_success(title, message, details={"Removed sessions": removed})


def _print_info_message(title: str, message: str) -> None:
    print_info(title, message)


def _print_sessions_info(message: str) -> None:
    _print_info_message("Sessions", message)


def _print_clean_aborted() -> None:
    _print_info_message("Clean", "Aborted.")


def _fail_unknown_session_status(console, status: str, session_status_cls, exc: Exception) -> None:
    console.print(f"[red]Unknown status: {status}[/red]")
    _print_valid_session_statuses(console, session_status_cls)
    raise typer.Exit(code=1) from exc


def _print_valid_session_statuses(console, session_status_cls) -> None:
    console.print(f"[dim]Valid: {', '.join(s.value for s in session_status_cls)}[/dim]")


def _print_session_op_output(console, value) -> None:
    console.print(value)


def _optional_output_path(output: str) -> Path | None:
    return Path(output) if output else None


def _run_result_path_op(
    session_id: str,
    op_name: str,
    op,
    *,
    success_message: str,
    error_title: str,
    error_msg: str,
    extra_exc: tuple[type[Exception], ...] = (),
) -> None:
    result_path = _run_session_op(
        session_id,
        op_name,
        op,
        error_title=error_title,
        error_msg=error_msg,
        extra_exc=extra_exc,
    )
    _print_result_path(success_message, result_path)


def _run_session_cleanup(
    store,
    *,
    age_seconds: int | None,
    statuses,
    title: str,
    message: str,
) -> None:
    removed = store.clean(older_than_seconds=age_seconds, statuses=statuses or None)
    _print_cleanup_result(title, message.format(removed=removed), removed)


def _run_session_update_op(
    session_id: str,
    op_name: str,
    op,
    *,
    error_title: str = "Operation failed",
    error_msg: str = "",
    extra_exc: tuple[type[Exception], ...] = (),
) -> None:
    session = _run_session_op(
        session_id,
        op_name,
        op,
        error_title=error_title,
        error_msg=error_msg,
        extra_exc=extra_exc,
    )
    _print_session_update(session_id, session)


def _session_submit_success_details(session) -> dict[str, str]:
    details = {
        "Session ID": session.id,
        "Name": session.name,
        "Target": session.target.value,
        "Status": session.status.value,
        "Workflow": session.workflow_file,
        "Execution scope": session.job_id or "full-workflow",
    }
    if session.target.value == "cloud":
        details["Auto destroy"] = (
            "Yes" if getattr(session, "auto_destroy", True) else "No"
        )
    if session.project:
        details["Project"] = session.project
    return details


def _parse_session_statuses(status_value: str, session_status_cls) -> list[object]:
    statuses: list[object] = []
    for raw in status_value.split(","):
        current = raw.strip()
        if not current:
            continue
        try:
            statuses.append(session_status_cls(current))
        except ValueError:
            error_exit("Invalid status", f"Unknown status: {current}")
    return statuses


# ======================================================================
# Submit
# ======================================================================


@app.command("submit")
def session_submit(
    workflow: Annotated[str, typer.Argument(help="Workflow file name or path")],
    job: Annotated[
        str, typer.Option("--job", "-j", help="Job ID to run (default: full workflow)")
    ] = "",
    local: Annotated[
        bool, typer.Option("--local", "-l", help="Run as local background process")
    ] = False,
    cloud: Annotated[
        str, typer.Option("--cloud", "-c", help="Cloud profile to use")
    ] = "",
    name: Annotated[str, typer.Option("--name", "-n", help="Session name/tag")] = "",
    inputs: Annotated[
        list[str] | None, typer.Option("--input", "-i", help="Input key=value pairs")
    ] = None,
):
    """Submit a workflow as a detached session."""
    console = get_console()

    (
        key_value_parser,
        cli_env_getter,
        cli_project_getter,
        session_target_cls,
        session_manager_cls,
    ) = _get_session_submit_deps()

    parsed_inputs: dict = key_value_parser(inputs or [])
    parsed_env: dict = cli_env_getter()

    session_project = _resolve_session_project(cli_project_getter)

    if cloud and local:
        error_exit("Invalid options", "Cannot use both --local and --cloud.")

    target = session_target_cls.CLOUD if cloud else session_target_cls.LOCAL
    mgr = session_manager_cls()

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
                project=session_project,
            )
        )
    except Exception as exc:
        error_exit("Submit failed", "Session submit failed.", details=str(exc))

    print_success(
        "Session submitted",
        "Session submitted successfully.",
        details=_session_submit_success_details(session),
    )
    console.print(_session_detail_table(session))
    print_info(
        "Next steps",
        "Useful follow-up commands.",
        details={
            "Check status": f"ofx session status {session.id}",
            "View logs": f"ofx session logs {session.id}",
            "Fetch results": f"ofx session fetch {session.id}",
        },
    )


# ======================================================================
# List
# ======================================================================


@app.command("list")
def session_list(
    status: Annotated[
        str, typer.Option("--status", "-s", help="Filter by status")
    ] = "",
    target: Annotated[
        str, typer.Option("--target", "-t", help="Filter: local or cloud")
    ] = "",
    project: Annotated[
        str, typer.Option("--project", help="Filter by project name")
    ] = "",
):
    """List all sessions."""
    console = get_console()
    store = _get_session_store_cls()()
    _status = None
    if status:
        session_status_cls = _get_session_status_cls()
        try:
            _status = session_status_cls(status)
        except ValueError as exc:
            _fail_unknown_session_status(console, status, session_status_cls, exc)

    sessions = store.list_sessions(
        status=_status, target=target or None, project=project or None
    )
    if not sessions:
        _print_sessions_info("No sessions found.")
        return

    table = Table(title="Sessions")
    for col, opts in [
        ("ID", {"style": "cyan", "no_wrap": True}),
        ("Name", {}),
        ("Project", {}),
        ("Target", {}),
        ("Status", {}),
        ("Workflow", {}),
        ("IP/Host", {}),
        ("PID", {}),
        ("Age", {"justify": "right"}),
    ]:
        table.add_column(col, **opts)  # type: ignore[arg-type]

    for s in sessions:
        ss = session_status_style(s.status.value)
        table.add_row(
            s.id,
            s.name or "-",
            s.project or "-",
            s.target.value,
            f"[{ss}]{s.status.value}[/{ss}]",
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
def session_status(session_id: Annotated[str, typer.Argument(help="Session ID")]):
    """Check the status of a session (probes PID if running)."""
    console = get_console()
    session = _run_session_op(session_id, "status", lambda mgr: mgr.status(session_id))
    _print_session_op_output(console, _session_detail_table(session))


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
    output = _run_session_op(
        session_id, "logs", lambda mgr: mgr.logs(session_id, tail=tail)
    )
    _print_session_op_output(console, output)


# ======================================================================
# Fetch
# ======================================================================


@app.command("fetch")
def session_fetch(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    passphrase: Annotated[
        str,
        typer.Option("--passphrase", "-p", help="Encrypt results with this passphrase"),
    ] = "",
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output directory")
    ] = "",
):
    """Fetch results from a completed session. Optionally encrypt with --passphrase."""
    output_dir = _optional_output_path(output)
    _run_result_path_op(
        session_id,
        "fetch",
        lambda mgr: mgr.fetch(session_id, passphrase=passphrase, output_dir=output_dir),
        success_message=(
            "Results fetched and encrypted." if passphrase else "Results fetched."
        ),
        error_title="Fetch failed",
        error_msg="Failed to fetch session results.",
        extra_exc=(RuntimeError,),
    )


# ======================================================================
# Decrypt
# ======================================================================


@app.command("decrypt")
def session_decrypt(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    passphrase: Annotated[
        str,
        typer.Option(
            "--passphrase",
            "-p",
            help="Decryption passphrase",
            prompt=True,
            hide_input=True,
        ),
    ],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output directory")
    ] = "",
):
    """Decrypt previously encrypted session results."""
    output_dir = _optional_output_path(output)
    _run_result_path_op(
        session_id,
        "decrypt",
        lambda mgr: mgr.decrypt(
            session_id, passphrase=passphrase, output_dir=output_dir
        ),
        success_message="Results decrypted.",
        error_title="Decrypt failed",
        error_msg="Failed to decrypt session results.",
        extra_exc=(RuntimeError, ValueError),
    )


# ======================================================================
# Cancel
# ======================================================================


@app.command("cancel")
def session_cancel(session_id: Annotated[str, typer.Argument(help="Session ID")]):
    """Cancel a running session (kills the process)."""
    _run_session_update_op(
        session_id,
        "cancel",
        lambda mgr: mgr.cancel(session_id),
    )


# ======================================================================
# Destroy
# ======================================================================


@app.command("destroy")
def session_destroy(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Force destroy even if running")
    ] = False,
):
    """Destroy a cloud session's VPS. For local, cleans up workspace."""
    _run_session_update_op(
        session_id,
        "destroy",
        lambda mgr: mgr.destroy(session_id, force=force),
        error_title="Destroy failed",
        error_msg="Failed to destroy session.",
        extra_exc=(RuntimeError,),
    )


# ======================================================================
# Clean
# ======================================================================


@app.command("clean")
def session_clean(
    older_than: Annotated[
        str, typer.Option("--older-than", help="Age threshold (e.g., 7d, 24h, 30m)")
    ] = "",
    status: Annotated[
        str, typer.Option("--status", "-s", help="Comma-separated statuses to clean")
    ] = "completed,fetched,encrypted,destroyed,canceled",
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
):
    """Remove old session data from disk."""
    console = get_console()
    store, session_status_cls = _get_session_store_and_status_deps()

    age_seconds = None
    if older_than:
        age_seconds = _parse_age_seconds_or_exit(older_than)

    statuses = _parse_session_statuses(status, session_status_cls)

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
        _print_sessions_info("No sessions match the criteria.")
        return

    console.print(f"[yellow]Will remove {len(matching)} session(s):[/yellow]")
    for sess in matching:
        console.print(
            f"  {sess.id}  {sess.name or '-'}  {sess.status.value}  {sess.age_display()}"
        )

    if not yes:
        if not typer.confirm("Proceed?"):
            _print_clean_aborted()
            return

    _run_session_cleanup(
        store,
        age_seconds=age_seconds,
        statuses=statuses,
        title="Clean",
        message="Removed {removed} session(s).",
    )


@app.command("guard")
def session_guard(
    older_than: Annotated[
        str, typer.Option("--older-than", help="Age threshold (e.g., 7d, 24h, 30m)")
    ] = "7d",
    status: Annotated[
        str, typer.Option("--status", "-s", help="Comma-separated statuses to clean")
    ] = "completed,fetched,encrypted,destroyed,canceled,failed",
):
    """Auto-cleanup guard for unattended environments (non-interactive)."""
    store, session_status_cls = _get_session_store_and_status_deps()
    age_seconds = _parse_age_seconds_or_exit(older_than)

    statuses = _parse_session_statuses(status, session_status_cls)

    _run_session_cleanup(
        store,
        age_seconds=age_seconds,
        statuses=statuses,
        title="Guard cleanup",
        message="Auto-cleanup completed.",
    )


@app.command("bundle")
def session_bundle(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output tar.gz path")
    ] = "",
):
    """Create a run artifacts bundle for a session (metadata + results)."""
    mgr = _get_session_manager_cls()()
    out_file = _optional_output_path(output)
    try:
        bundle = asyncio.run(mgr.bundle_artifacts(session_id, output_file=out_file))
    except Exception as exc:
        error_exit(
            "Bundle failed", "Could not create artifacts bundle.", details=str(exc)
        )
    _print_success_path("Bundle created", "Run artifacts bundle created.", bundle)
