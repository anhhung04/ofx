"""Cloud fleet management commands."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.cloud.helpers import create_cloud_provider, run_cloud_sync
from ofx.commands.project.project_manager import ProjectManager
from ofx.commands.ui_helpers import session_status_style
from ofx.settings import get_console

logger = logging.getLogger(__name__)

FleetDistributor = None
FleetInputParser = None
CloudConfig = None
CloudProviderRegistry = None
TEMP_DIR = None
encrypt_results = None
ensure_dir = None
get_cloud_profile_manager = None
get_cli_project = None
get_cli_env_vars = None
parse_key_value_pairs = None
SessionManager = None
SessionStore = None
SessionTarget = None

fleet_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud fleet (multiple instances)"
)

async def _refresh_sessions(mgr, sessions: list):
    """Best-effort status refresh; keep original session on failure."""
    refreshed = []
    for s in sessions:
        try:
            refreshed.append(await mgr.status(s.id))
        except (RuntimeError, OSError, TimeoutError, ValueError):
            logger.warning("Failed to refresh session %s, using cached state", s.id)
            refreshed.append(s)
    return refreshed

def _get_session_store_cls():
    session_store_cls = SessionStore
    if session_store_cls is None:
        from ofx.cloud.sessions import SessionStore as session_store_cls
    return session_store_cls

def _get_session_manager_cls():
    session_manager_cls = SessionManager
    if session_manager_cls is None:
        from ofx.cloud.sessions import SessionManager as session_manager_cls
    return session_manager_cls

def _get_session_target_cls():
    session_target_cls = SessionTarget
    if session_target_cls is None:
        from ofx.cloud.sessions import SessionTarget as session_target_cls
    return session_target_cls

def _get_fleet_run_deps():
    key_value_parser = parse_key_value_pairs
    if key_value_parser is None:
        from ofx.utils.args import parse_key_value_pairs as key_value_parser

    cli_env_getter = get_cli_env_vars
    if cli_env_getter is None:
        from ofx.commands import get_cli_env_vars as cli_env_getter

    project_getter = get_cli_project
    if project_getter is None:
        from ofx.commands import get_cli_project as project_getter

    fleet_input_parser_cls = FleetInputParser
    if fleet_input_parser_cls is None:
        from ofx.cloud.fleet_input import FleetInputParser as fleet_input_parser_cls

    fleet_distributor_cls = FleetDistributor
    if fleet_distributor_cls is None:
        from ofx.cloud.fleet_distributor import FleetDistributor as fleet_distributor_cls

    return (
        key_value_parser,
        cli_env_getter,
        project_getter,
        fleet_input_parser_cls,
        fleet_distributor_cls,
    )

def _get_fleet_create_deps():
    provider_registry = CloudProviderRegistry
    if provider_registry is None:
        from ofx.cloud import CloudProviderRegistry as provider_registry

    profile_manager_getter = get_cloud_profile_manager
    if profile_manager_getter is None:
        from ofx.cloud.config import (
            get_cloud_profile_manager as profile_manager_getter,
        )

    cloud_config_cls = CloudConfig
    if cloud_config_cls is None:
        from ofx.models.cloud import CloudConfig as cloud_config_cls

    return provider_registry, profile_manager_getter, cloud_config_cls

def _get_fleet_temp_dir_deps():
    temp_dir = TEMP_DIR
    ensure_dir_fn = ensure_dir
    if temp_dir is None or ensure_dir_fn is None:
        from ofx.settings import TEMP_DIR as temp_dir, ensure_dir as ensure_dir_fn

    return temp_dir, ensure_dir_fn

def _get_encrypt_results_fn():
    encrypt_results_fn = encrypt_results
    if encrypt_results_fn is None:
        from ofx.cloud.sessions.encryption import encrypt_results as encrypt_results_fn

    return encrypt_results_fn

def _apply_fleet_profile_defaults(
    profile: str,
    provider: str,
    region: str,
    size: str,
    image: str,
    profile_manager_getter,
) -> tuple[str, str, str, str]:
    if not profile:
        return provider, region, size, image

    cfg = profile_manager_getter().as_cloud_config(profile)
    if cfg is None:
        return provider, region, size, image

    return (
        provider or cfg.provider or "",
        region or cfg.region or "",
        size or cfg.size or "",
        image or cfg.image or "",
    )

def _fail_missing_fleet_sessions(console, fleet_group_id: str) -> None:
    console.print(f"[red]No sessions found for fleet group '{fleet_group_id}'[/red]")
    raise typer.Exit(code=1)

def _print_dim_empty(console, message: str) -> None:
    console.print(f"[dim]{message}[/dim]")

def _fail_red(console, message: str, code: int = 1) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=code)

def _print_fleet_followups(console, fleet_group_id: str) -> None:
    console.print(f"[dim]Fleet status:  ofx cloud fleet status {fleet_group_id}[/dim]")
    console.print(f"[dim]Fleet results: ofx cloud fleet results {fleet_group_id}[/dim]")

def _resolve_fleet_project(project_getter) -> str:
    fleet_project = project_getter()
    if fleet_project:
        return fleet_project

    active_path = ProjectManager.get_active_path()
    return active_path.name if active_path else ""

def _load_fleet_sessions(fleet_group_id: str):
    session_store_cls = _get_session_store_cls()
    store = session_store_cls()
    sessions = store.list_by_fleet_group(fleet_group_id)
    return store, sessions

def _load_fleet_sessions_or_exit(console, fleet_group_id: str):
    store, sessions = _load_fleet_sessions(fleet_group_id)
    if not sessions:
        _fail_missing_fleet_sessions(console, fleet_group_id)
    return store, sessions

def _refresh_fleet_sessions(console, store, sessions: list, status_message: str):
    session_manager_cls = _get_session_manager_cls()
    mgr = session_manager_cls(store=store)
    with console.status(status_message):
        sessions = asyncio.run(_refresh_sessions(mgr, sessions))
    return mgr, sessions

def _fleet_results_summary(completed: list, failed: list, running: list, fetchable: list) -> str:
    return (
        f"  Completed: {len(completed)}  Failed: {len(failed)}  "
        f"Running: {len(running)}  Fetchable: {len(fetchable)}"
    )

def _print_fleet_fetch_summary(console, fetched: int, total: int, agg_dir: Path, enc_path: Path | None = None) -> None:
    if total == 0:
        _print_dim_empty(console, "No results to fetch.")
        return

    console.print()
    console.print(f"[green]Fetched {fetched}/{total} session results → {agg_dir}[/green]")
    if enc_path is not None:
        console.print(f"[green]Encrypted → {enc_path}[/green]")

def _print_fleet_cancel_summary(console, canceled: int, total: int) -> None:
    console.print(f"[yellow]Canceled {canceled}/{total} sessions.[/yellow]")

def _print_destroyed_instances(console, destroyed: int, total: int) -> None:
    console.print(f"[green]Destroyed {destroyed}/{total} instances.[/green]")

def _print_fleet_ready(console, total: int) -> None:
    console.print(f"[green]Fleet of {total} instances ready.[/green]")

def _print_created_instance(console, instance_id: str) -> None:
    console.print(f"  [dim]Created {instance_id}[/dim]")

def _print_create_failure(console, instance_name: str, exc: Exception) -> None:
    console.print(f"  [red]Failed to create {instance_name}: {exc}[/red]")

def _print_ready_instance(console, instance_id: str, ip: str | None) -> None:
    console.print(f"  [green]{instance_id}[/green] → {ip or 'no IP'}")

def _print_create_wait_warning(console, instance_id: str, exc: Exception) -> None:
    console.print(f"  [yellow]{instance_id}: {exc}[/yellow]")

def _print_waiting_for_instances(console, count: int) -> None:
    console.print(f"[dim]Waiting for {count} instances...[/dim]")

def _print_destroy_target_heading(console, total: int) -> None:
    console.print(f"Found {total} instances to destroy:")

def _select_destroy_targets(all_instances: list, tag: str, prefix: str) -> list:
    targets = []
    for inst in all_instances:
        if tag and tag in (inst.tags or []):
            targets.append(inst)
        elif prefix and inst.name and inst.name.startswith(prefix):
            targets.append(inst)
    return targets

def _print_destroy_targets(console, targets: list) -> None:
    _print_destroy_target_heading(console, len(targets))
    for inst in targets:
        console.print(f"  {inst.instance_id} ({inst.name}) → {inst.ip or 'no IP'}")

def _print_running_session_count(console, count: int, suffix: str) -> None:
    console.print(f"[yellow]{count} session(s) {suffix}[/yellow]")

def _fail_no_submitted_sessions(console) -> None:
    console.print("[red]No sessions submitted.[/red]")
    raise typer.Exit(code=1)

def _fail_no_instances_created(console) -> None:
    console.print("[red]No instances created.[/red]")
    raise typer.Exit(code=1)

def _print_fleet_submission_summary(console, sessions: list, effective_count: int, fleet_group_id: str) -> None:
    console.print()
    if not sessions:
        _fail_no_submitted_sessions(console)

    console.print(
        f"[green]{len(sessions)}/{effective_count} sessions submitted.[/green]"
    )
    console.print()
    _print_fleet_followups(console, fleet_group_id)

def _resolve_project_results_dir(fetchable: list, fleet_group_id: str) -> Path | None:
    fleet_proj = next((s.project for s in fetchable if s.project), "")
    if not fleet_proj:
        return None

    try:
        proj_path = Path(ProjectManager.resolve_path(fleet_proj))
    except (ValueError, OSError):
        logger.warning("Could not resolve project path for '%s'", fleet_proj)
        return None

    if not proj_path.exists():
        return None

    return proj_path / "evidence" / "sessions" / f"fleet-{fleet_group_id}"

def _resolve_fleet_results_dir(output: str, fetchable: list, fleet_group_id: str) -> Path:
    if output:
        return Path(output)

    project_results_dir = _resolve_project_results_dir(fetchable, fleet_group_id)
    if project_results_dir is not None:
        return project_results_dir

    temp_dir, ensure_dir_fn = _get_fleet_temp_dir_deps()
    return ensure_dir_fn(temp_dir) / f"fleet-{fleet_group_id}"

async def _create_fleet_instances(
    console,
    cloud,
    cloud_config_cls,
    *,
    count: int,
    name_prefix: str,
    provider: str,
    region: str,
    size: str,
    image: str,
):
    instances = []
    for i in range(count):
        instance_name = f"{name_prefix}-{i}"
        cfg = cloud_config_cls(
            provider=provider,
            region=region,
            size=size,
            image=image,
        )
        try:
            inst = await cloud.create_instance(cfg)
            instances.append(inst)
            _print_created_instance(console, inst.instance_id)
        except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
            _print_create_failure(console, instance_name, exc)
    return instances

async def _wait_for_fleet_instances(console, cloud, instances: list) -> None:
    for inst in instances:
        try:
            await cloud.wait_until_ready(inst.instance_id)
            refreshed = await cloud.get_instance(inst.instance_id)
            if refreshed:
                _print_ready_instance(console, refreshed.instance_id, refreshed.ip)
        except (RuntimeError, TimeoutError, OSError) as exc:
            _print_create_wait_warning(console, inst.instance_id, exc)

async def _submit_fleet_sessions(
    console,
    mgr,
    session_target_cls,
    *,
    workflow: str,
    job: str,
    profile: str,
    parsed_inputs: dict,
    parsed_env: dict,
    fleet_project: str,
    effective_count: int,
    chunk_paths: list[Path],
    target_var: str,
    fleet_group_id: str,
    fleet_name: str,
):
    sessions = []
    for i in range(effective_count):
        instance_inputs = dict(parsed_inputs)
        if chunk_paths and i < len(chunk_paths):
            instance_inputs[target_var] = str(chunk_paths[i])

        session_name = f"{fleet_name}-{i}"
        try:
            session = await mgr.submit(
                workflow,
                job_id=job,
                target=session_target_cls.CLOUD,
                cloud_profile=profile,
                inputs=instance_inputs,
                name=session_name,
                env=parsed_env,
                tags={
                    "fleet_group": fleet_group_id,
                    "fleet_index": str(i),
                },
                project=fleet_project,
            )
            session = session.model_copy(
                update={
                    "fleet_group_id": fleet_group_id,
                    "fleet_index": i,
                    "fleet_total": effective_count,
                }
            )
            mgr.store.save(session)
            sessions.append(session)
            console.print(
                f"  [green]#{i}[/green] session={session.id} "
                f"ip={session.instance_ip or 'pending'}"
            )
        except (RuntimeError, OSError, TimeoutError, ValueError, FileNotFoundError) as exc:
            console.print(f"  [red]#{i} failed: {exc}[/red]")
    return sessions

def _prepare_fleet_run_targets(
    console,
    distributor,
    *,
    target_list: list,
    count: int,
    distribution: str,
) -> tuple[int, list[Path], Path | None]:
    import tempfile

    chunk_paths: list[Path] = []
    temp_dir: Path | None = None
    if not target_list:
        return count, chunk_paths, temp_dir

    chunks = distributor.distribute(target_list, count, distribution)
    effective_count = len(chunks)
    if effective_count == 0:
        console.print(
            "[red]Fleet: no targets after parsing/exclusion. Check --targets.[/red]"
        )
        raise typer.Exit(code=1)

    temp_dir = Path(tempfile.mkdtemp(prefix="ofx_fleet_run_"))
    for i, chunk in enumerate(chunks):
        chunk_file = temp_dir / f"fleet_chunk_{i}.txt"
        chunk_file.write_text("\n".join(chunk) + "\n")
        chunk_paths.append(chunk_file)

    return effective_count, chunk_paths, temp_dir

@fleet_app.command("create")
def fleet_create(
    count: Annotated[int, typer.Argument(help="Number of instances to create")],
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    name_prefix: Annotated[
        str, typer.Option("--prefix", help="Instance name prefix")
    ] = "ofx-fleet",
    region: Annotated[str, typer.Option("--region", "-r", help="Region")] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
):
    """Create a fleet of cloud instances."""
    console = get_console()
    provider_registry, profile_manager_getter, cloud_config_cls = (
        _get_fleet_create_deps()
    )

    provider, region, size, image = _apply_fleet_profile_defaults(
        profile,
        provider,
        region,
        size,
        image,
        profile_manager_getter,
    )

    if not provider:
        _fail_red(console, "Specify --provider or --profile")

    cloud = provider_registry.create(provider)

    with console.status(f"Creating {count} instances..."):
        instances = asyncio.run(
            _create_fleet_instances(
                console,
                cloud,
                cloud_config_cls,
                count=count,
                name_prefix=name_prefix,
                provider=provider,
                region=region,
                size=size,
                image=image,
            )
        )

    if not instances:
        _fail_no_instances_created(console)

    _print_waiting_for_instances(console, len(instances))
    asyncio.run(_wait_for_fleet_instances(console, cloud, instances))

    _print_fleet_ready(console, len(instances))

@fleet_app.command("run")
def fleet_run(
    workflow: Annotated[str, typer.Argument(help="Workflow file name or path")],
    targets: Annotated[
        str,
        typer.Option(
            "--targets", "-t", help="Targets: file path, CIDR, comma-separated IPs"
        ),
    ] = "",
    count: Annotated[
        int, typer.Option("--count", "-n", help="Number of fleet instances (auto if 0)")
    ] = 0,
    profile: Annotated[str, typer.Option("--profile", help="Cloud profile")] = "",
    distribution: Annotated[
        str,
        typer.Option(
            "--distribution",
            "-d",
            help="Distribution mode: chunk, round-robin, subnet, line",
        ),
    ] = "chunk",
    job: Annotated[str, typer.Option("--job", "-j", help="Job ID to run")] = "",
    name: Annotated[str, typer.Option("--name", help="Fleet run name")] = "",
    inputs: Annotated[
        list[str], typer.Option("--input", "-i", help="Input key=value pairs")
    ] = [],
    target_var: Annotated[
        str,
        typer.Option(
            "--target-var", help="Input variable name for the target chunk file"
        ),
    ] = "targets_file",
):
    """Submit a workflow across multiple fleet instances with target distribution.

    Each instance gets a chunk of the targets. Use --target-var to control
    which workflow input receives the chunk file path (default: targets_file).

    Examples:
        ofx cloud fleet run scan.yml --targets targets.txt --count 5 --profile do-nyc
        ofx cloud fleet run scan.yml --targets 10.0.0.0/24 --count 10 --distribution round-robin
    """
    console = get_console()
    import secrets as _secrets

    if inputs is None:
        inputs = []

    (
        key_value_parser,
        cli_env_getter,
        project_getter,
        fleet_input_parser_cls,
        fleet_distributor_cls,
    ) = _get_fleet_run_deps()

    parsed_inputs: dict = key_value_parser(inputs)
    parsed_env: dict = cli_env_getter()

    fleet_project = _resolve_fleet_project(project_getter)

    if not profile:
        _fail_red(console, "Fleet run requires --profile for cloud execution")

    parser = fleet_input_parser_cls()
    target_list = parser.parse(targets) if targets else []

    if count == 0:
        if target_list:
            count = min(len(target_list), 10)
        else:
            count = 1

    distributor = fleet_distributor_cls()
    effective_count, chunk_paths, temp_dir = _prepare_fleet_run_targets(
        console,
        distributor,
        target_list=target_list,
        count=count,
        distribution=distribution,
    )

    fleet_group_id = _secrets.token_hex(4)
    fleet_name = name or f"fleet-{fleet_group_id}"

    console.print(f"[bold]Fleet run:[/bold] {fleet_name}")
    console.print(f"  Workflow:     {workflow}")
    console.print(f"  Instances:    {effective_count}")
    if target_list:
        console.print(f"  Targets:      {len(target_list)} ({distribution})")
    console.print(f"  Profile:      {profile}")
    console.print(f"  Fleet group:  {fleet_group_id}")
    console.print()

    session_manager_cls = _get_session_manager_cls()
    session_target_cls = _get_session_target_cls()

    mgr = session_manager_cls()

    with console.status("Submitting fleet sessions..."):
        try:
            sessions = asyncio.run(
                _submit_fleet_sessions(
                    console,
                    mgr,
                    session_target_cls,
                    workflow=workflow,
                    job=job,
                    profile=profile,
                    parsed_inputs=parsed_inputs,
                    parsed_env=parsed_env,
                    fleet_project=fleet_project,
                    effective_count=effective_count,
                    chunk_paths=chunk_paths,
                    target_var=target_var,
                    fleet_group_id=fleet_group_id,
                    fleet_name=fleet_name,
                )
            )
        finally:
            if temp_dir:
                import shutil as _shutil

                _shutil.rmtree(temp_dir, ignore_errors=True)

    _print_fleet_submission_summary(
        console, sessions, effective_count, fleet_group_id
    )

@fleet_app.command("status")
def fleet_status(
    fleet_group_id: Annotated[str, typer.Argument(help="Fleet group ID")],
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh", "-r", help="Probe running sessions for latest status"
        ),
    ] = False,
):
    """Show status of all sessions in a fleet group."""
    console = get_console()
    store, sessions = _load_fleet_sessions_or_exit(console, fleet_group_id)

    if refresh:
        _mgr, sessions = _refresh_fleet_sessions(
            console, store, sessions, "Refreshing session statuses..."
        )

    status_counts: dict[str, int] = {}
    for s in sessions:
        status_counts[s.status.value] = status_counts.get(s.status.value, 0) + 1

    fleet_name = sessions[0].name.rsplit("-", 1)[0] if sessions else fleet_group_id
    console.print(f"[bold]Fleet:[/bold] {fleet_name}  [dim]({fleet_group_id})[/dim]")
    console.print(
        f"  Total: {len(sessions)}  |  "
        + "  ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))
    )
    console.print()

    table = Table(title="Fleet Sessions")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("IP/Host")
    table.add_column("PID")
    table.add_column("Age", justify="right")
    table.add_column("Error")

    for s in sessions:
        idx = str(s.fleet_index) if s.fleet_index >= 0 else "-"
        status_style = session_status_style(s.status.value)
        table.add_row(
            idx,
            s.id,
            f"[{status_style}]{s.status.value}[/{status_style}]",
            s.instance_ip or "(local)",
            str(s.remote_pid) if s.remote_pid else "-",
            s.age_display(),
            (s.error[:40] + "...") if len(s.error) > 40 else s.error,
        )

    console.print(table)

@fleet_app.command("results")
def fleet_results(
    fleet_group_id: Annotated[str, typer.Argument(help="Fleet group ID")],
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output directory for aggregated results"),
    ] = "",
    passphrase: Annotated[
        str, typer.Option("--passphrase", "-p", help="Encrypt results with passphrase")
    ] = "",
    skip_running: Annotated[
        bool,
        typer.Option(
            "--skip-running", help="Skip sessions still running (fetch completed only)"
        ),
    ] = False,
):
    """Fetch and aggregate results from all sessions in a fleet group.

    Downloads results from each completed session into a subdirectory
    named by fleet index. Optionally encrypts the aggregate.
    """
    console = get_console()
    store, sessions = _load_fleet_sessions_or_exit(console, fleet_group_id)

    mgr, sessions = _refresh_fleet_sessions(
        console, store, sessions, "Checking fleet session statuses..."
    )

    running = [s for s in sessions if s.is_running()]
    completed = [s for s in sessions if s.status.value == "completed"]
    failed = [s for s in sessions if s.status.value == "failed"]
    fetchable = [
        s for s in sessions if s.is_done() and s.status.value not in ("destroyed",)
    ]

    console.print(f"[bold]Fleet results:[/bold] {fleet_group_id}")
    console.print(_fleet_results_summary(completed, failed, running, fetchable))

    if running and not skip_running:
        _print_running_session_count(console, len(running), "still running. Use --skip-running to fetch only completed.")
        raise typer.Exit(code=1)

    if not fetchable:
        _print_fleet_fetch_summary(console, 0, 0, agg_dir=Path("."))
        return

    agg_dir = _resolve_fleet_results_dir(output, fetchable, fleet_group_id)
    agg_dir.mkdir(parents=True, exist_ok=True)

    async def _fetch_all():
        fetched = 0
        for s in fetchable:
            idx_label = str(s.fleet_index) if s.fleet_index >= 0 else s.id
            dest = agg_dir / f"instance-{idx_label}"
            try:
                await mgr.fetch(s.id, output_dir=dest)
                fetched += 1
                console.print(f"  [green]#{idx_label}[/green] → {dest}")
            except (RuntimeError, OSError, TimeoutError) as exc:
                console.print(f"  [red]#{idx_label} fetch failed: {exc}[/red]")
        return fetched

    console.print()
    fetched = asyncio.run(_fetch_all())

    enc_path = None
    if passphrase:
        enc_path = _get_encrypt_results_fn()(agg_dir, passphrase)

    _print_fleet_fetch_summary(console, fetched, len(fetchable), agg_dir, enc_path)

@fleet_app.command("cancel")
def fleet_cancel(
    fleet_group_id: Annotated[str, typer.Argument(help="Fleet group ID")],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Cancel all running sessions in a fleet group."""
    console = get_console()
    store, sessions = _load_fleet_sessions_or_exit(console, fleet_group_id)

    running = [s for s in sessions if s.is_running()]
    if not running:
        _print_dim_empty(console, "No running sessions to cancel.")
        return

    _print_running_session_count(console, len(running), "running session(s) to cancel.")
    if not force:
        confirm = typer.confirm("Cancel all?")
        if not confirm:
            raise typer.Abort()

    session_manager_cls = _get_session_manager_cls()

    mgr = session_manager_cls(store=store)

    async def _cancel_all():
        canceled = 0
        for s in running:
            try:
                await mgr.cancel(s.id)
                canceled += 1
            except (RuntimeError, OSError) as exc:
                console.print(f"  [red]{s.id} cancel failed: {exc}[/red]")
        return canceled

    canceled = asyncio.run(_cancel_all())
    _print_fleet_cancel_summary(console, canceled, len(running))

@fleet_app.command("destroy")
def fleet_destroy(
    tag: Annotated[
        str, typer.Option("--tag", help="Destroy instances with this tag")
    ] = "",
    prefix: Annotated[
        str, typer.Option("--prefix", help="Destroy instances matching name prefix")
    ] = "ofx-fleet",
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Destroy fleet instances by tag or name prefix."""
    console = get_console()
    _, cloud = create_cloud_provider(profile, provider)
    all_instances = run_cloud_sync(
        "list instances", lambda: asyncio.run(cloud.list_instances())
    )

    targets = _select_destroy_targets(all_instances, tag, prefix)

    if not targets:
        _print_dim_empty(console, "No matching instances found.")
        return

    _print_destroy_targets(console, targets)

    if not force:
        confirm = typer.confirm(f"Destroy {len(targets)} instances?")
        if not confirm:
            raise typer.Abort()

    async def _destroy_all():
        count = 0
        for inst in targets:
            try:
                await cloud.destroy_instance(inst.instance_id)
                count += 1
            except (RuntimeError, OSError, TimeoutError) as e:
                console.print(f"  [red]Failed to destroy {inst.instance_id}: {e}[/red]")
        return count

    destroyed = asyncio.run(_destroy_all())

    _print_destroyed_instances(console, destroyed, len(targets))
