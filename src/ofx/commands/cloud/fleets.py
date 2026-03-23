"""Cloud fleet management commands."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.cloud.helpers import create_cloud_provider, run_cloud_sync
from ofx.commands.ui_helpers import session_status_style
from ofx.settings import get_console

fleet_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud fleet (multiple instances)"
)


def _resolve_active_project_name() -> str:
    """Resolve active project name from global flag or active project."""
    from ofx.commands import get_cli_project

    project = get_cli_project()
    if project:
        return project
    from ofx.commands.project.project_manager import ProjectManager

    active_path = ProjectManager.get_active_path()
    return active_path.name if active_path else ""


def _fleet_group_not_found(console, fleet_group_id: str) -> None:
    console.print(f"[red]No sessions found for fleet group '{fleet_group_id}'[/red]")
    raise typer.Exit(code=1)


async def _refresh_sessions(mgr, sessions: list):
    """Best-effort status refresh; keep original session on failure."""
    refreshed = []
    for s in sessions:
        try:
            refreshed.append(await mgr.status(s.id))
        except Exception:
            refreshed.append(s)
    return refreshed


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
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        cfg = mgr.as_cloud_config(profile)
        if cfg:
            provider = provider or cfg.provider or ""
            region = region or cfg.region or ""
            size = size or cfg.size or ""
            image = image or cfg.image or ""

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    from ofx.models.cloud import CloudConfig

    cloud = CloudProviderRegistry.create(provider)

    async def _create_fleet():
        instances = []
        for i in range(count):
            iname = f"{name_prefix}-{i}"
            cfg = CloudConfig(
                provider=provider,
                region=region,
                size=size,
                image=image,
            )
            try:
                inst = await cloud.create_instance(cfg)
                instances.append(inst)
                console.print(f"  [dim]Created {inst.instance_id}[/dim]")
            except Exception as e:
                console.print(f"  [red]Failed to create {iname}: {e}[/red]")
        return instances

    with console.status(f"Creating {count} instances..."):
        instances = asyncio.run(_create_fleet())

    if not instances:
        console.print("[red]No instances created.[/red]")
        raise typer.Exit(code=1)

    async def _wait_all():
        for inst in instances:
            try:
                await cloud.wait_until_ready(inst.instance_id)
                refreshed = await cloud.get_instance(inst.instance_id)
                if refreshed:
                    console.print(
                        f"  [green]{refreshed.instance_id}[/green] → {refreshed.ip or 'no IP'}"
                    )
            except Exception as e:
                console.print(f"  [yellow]{inst.instance_id}: {e}[/yellow]")

    # Wait for all
    console.print(f"[dim]Waiting for {len(instances)} instances...[/dim]")
    asyncio.run(_wait_all())

    console.print(f"[green]Fleet of {len(instances)} instances ready.[/green]")


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
    ] = [],  # noqa: B006
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
    import tempfile

    from ofx.cloud.fleet_distributor import FleetDistributor
    from ofx.cloud.fleet_input import FleetInputParser
    from ofx.cloud.sessions import SessionManager, SessionTarget
    from ofx.commands import get_cli_env_vars
    from ofx.utils.args import parse_key_value_pairs

    if inputs is None:
        inputs = []

    parsed_inputs: dict = parse_key_value_pairs(inputs)
    parsed_env: dict = get_cli_env_vars()

    # Resolve project: global -p > active project
    fleet_project = _resolve_active_project_name()

    if not profile:
        console.print("[red]Fleet run requires --profile for cloud execution[/red]")
        raise typer.Exit(code=1)

    # Parse and distribute targets
    parser = FleetInputParser()
    target_list = parser.parse(targets) if targets else []

    if count == 0:
        if target_list:
            count = min(len(target_list), 10)  # sensible default cap
        else:
            count = 1

    # Write per-instance chunk files so sessions receive valid file paths
    distributor = FleetDistributor()
    chunk_paths: list[Path] = []
    temp_dir: Path | None = None
    if target_list:
        chunks = distributor.distribute(target_list, count, distribution)
        effective_count = len(chunks)
        if effective_count == 0:
            console.print("[red]Fleet: no targets after parsing/exclusion. Check --targets.[/red]")
            raise typer.Exit(code=1)
        temp_dir = Path(tempfile.mkdtemp(prefix="ofx_fleet_run_"))
        for i, chunk in enumerate(chunks):
            chunk_file = temp_dir / f"fleet_chunk_{i}.txt"
            chunk_file.write_text("\n".join(chunk) + "\n")
            chunk_paths.append(chunk_file)
    else:
        effective_count = count

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

    mgr = SessionManager()

    async def _submit_fleet():
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
                    target=SessionTarget.CLOUD,
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
                # Update with fleet metadata
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
            except Exception as exc:
                console.print(f"  [red]#{i} failed: {exc}[/red]")
        return sessions

    with console.status("Submitting fleet sessions..."):
        try:
            sessions = asyncio.run(_submit_fleet())
        finally:
            # Chunk files have been uploaded by the session manager — safe to remove
            if temp_dir:
                import shutil as _shutil
                _shutil.rmtree(temp_dir, ignore_errors=True)

    console.print()
    if not sessions:
        console.print("[red]No sessions submitted.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[green]{len(sessions)}/{effective_count} sessions submitted.[/green]"
    )
    console.print()
    console.print(f"[dim]Fleet status:  ofx cloud fleet status {fleet_group_id}[/dim]")
    console.print(f"[dim]Fleet results: ofx cloud fleet results {fleet_group_id}[/dim]")


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
    from ofx.cloud.sessions import SessionManager, SessionStore

    store = SessionStore()
    sessions = store.list_by_fleet_group(fleet_group_id)

    if not sessions:
        _fleet_group_not_found(console, fleet_group_id)

    if refresh:
        mgr = SessionManager(store=store)

        with console.status("Refreshing session statuses..."):
            sessions = asyncio.run(_refresh_sessions(mgr, sessions))

    # Summary counts
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
    from ofx.cloud.sessions import SessionManager, SessionStore

    store = SessionStore()
    sessions = store.list_by_fleet_group(fleet_group_id)

    if not sessions:
        _fleet_group_not_found(console, fleet_group_id)

    # Refresh statuses first
    mgr = SessionManager(store=store)

    with console.status("Checking fleet session statuses..."):
        sessions = asyncio.run(_refresh_sessions(mgr, sessions))

    running = [s for s in sessions if s.is_running()]
    completed = [s for s in sessions if s.status.value == "completed"]
    failed = [s for s in sessions if s.status.value == "failed"]
    fetchable = [
        s for s in sessions if s.is_done() and s.status.value not in ("destroyed",)
    ]

    console.print(f"[bold]Fleet results:[/bold] {fleet_group_id}")
    console.print(
        f"  Completed: {len(completed)}  Failed: {len(failed)}  "
        f"Running: {len(running)}  Fetchable: {len(fetchable)}"
    )

    if running and not skip_running:
        console.print(
            f"[yellow]{len(running)} session(s) still running. "
            f"Use --skip-running to fetch only completed.[/yellow]"
        )
        raise typer.Exit(code=1)

    if not fetchable:
        console.print("[dim]No results to fetch.[/dim]")
        return

    # Determine output dir
    if output:
        agg_dir = Path(output)
    else:
        # Check if fleet sessions have a project — route results there
        fleet_proj = next((s.project for s in fetchable if s.project), "")
        if fleet_proj:
            try:
                from ofx.commands.project.project_manager import ProjectManager

                proj_path = Path(ProjectManager.resolve_path(fleet_proj))
                if proj_path.exists():
                    agg_dir = proj_path / "evidence" / "sessions" / f"fleet-{fleet_group_id}"
                else:
                    fleet_proj = ""
            except Exception:
                fleet_proj = ""
        if not fleet_proj:
            from ofx.settings import TEMP_DIR, ensure_dir

            agg_dir = ensure_dir(TEMP_DIR) / f"fleet-{fleet_group_id}"
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
            except Exception as exc:
                console.print(f"  [red]#{idx_label} fetch failed: {exc}[/red]")
        return fetched

    console.print()
    fetched = asyncio.run(_fetch_all())

    console.print()
    console.print(
        f"[green]Fetched {fetched}/{len(fetchable)} session results → {agg_dir}[/green]"
    )

    if passphrase:
        from ofx.cloud.sessions.encryption import encrypt_results

        enc_path = encrypt_results(agg_dir, passphrase)
        console.print(f"[green]Encrypted → {enc_path}[/green]")


@fleet_app.command("cancel")
def fleet_cancel(
    fleet_group_id: Annotated[str, typer.Argument(help="Fleet group ID")],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Cancel all running sessions in a fleet group."""
    console = get_console()
    from ofx.cloud.sessions import SessionManager, SessionStore

    store = SessionStore()
    sessions = store.list_by_fleet_group(fleet_group_id)

    if not sessions:
        _fleet_group_not_found(console, fleet_group_id)

    running = [s for s in sessions if s.is_running()]
    if not running:
        console.print("[dim]No running sessions to cancel.[/dim]")
        return

    console.print(f"[yellow]{len(running)} running session(s) to cancel.[/yellow]")
    if not force:
        confirm = typer.confirm("Cancel all?")
        if not confirm:
            raise typer.Abort()

    mgr = SessionManager(store=store)

    async def _cancel_all():
        canceled = 0
        for s in running:
            try:
                await mgr.cancel(s.id)
                canceled += 1
            except Exception as exc:
                console.print(f"  [red]{s.id} cancel failed: {exc}[/red]")
        return canceled

    canceled = asyncio.run(_cancel_all())
    console.print(f"[yellow]Canceled {canceled}/{len(running)} sessions.[/yellow]")


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
    all_instances = run_cloud_sync("list instances", lambda: asyncio.run(cloud.list_instances()))

    # Filter by tag or prefix
    targets = []
    for inst in all_instances:
        if tag and tag in (inst.tags or []):
            targets.append(inst)
        elif prefix and inst.name and inst.name.startswith(prefix):
            targets.append(inst)

    if not targets:
        console.print("[dim]No matching instances found.[/dim]")
        return

    console.print(f"Found {len(targets)} instances to destroy:")
    for inst in targets:
        console.print(f"  {inst.instance_id} ({inst.name}) → {inst.ip or 'no IP'}")

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
            except Exception as e:
                console.print(f"  [red]Failed to destroy {inst.instance_id}: {e}[/red]")
        return count

    destroyed = asyncio.run(_destroy_all())

    console.print(f"[green]Destroyed {destroyed}/{len(targets)} instances.[/green]")
