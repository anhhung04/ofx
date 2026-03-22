"""Cloud management CLI commands for OFX.

Provides commands to manage cloud profiles, instances, and images.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.ui_helpers import print_error, print_warning
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "cloud"
HELP = "Manage cloud profiles, instances, and images"


# ---------------------------------------------------------------------------
# Profile management
# ---------------------------------------------------------------------------

profile_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud configuration profiles"
)
app.add_typer(profile_app, name="profile")


@profile_app.command("list")
def profile_list():
    """List all configured cloud profiles."""
    console = get_console()
    from ofx.cloud.config import get_cloud_profile_manager

    mgr = get_cloud_profile_manager()
    profiles = mgr.list_profiles()
    default = mgr.default_profile_name

    if not profiles:
        console.print("[dim]No cloud profiles configured.[/dim]")
        console.print("Add one with: [bold]ofx cloud profile add <name>[/bold]")
        return

    table = Table(title="Cloud Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Provider")
    table.add_column("Region")
    table.add_column("Size")
    table.add_column("Image")
    table.add_column("Default", justify="center")

    for name in sorted(profiles):
        data = mgr.get_profile_data(name) or {}
        table.add_row(
            name,
            data.get("provider", ""),
            data.get("region", ""),
            data.get("size", ""),
            data.get("image", ""),
            "✓" if name == default else "",
        )

    console.print(table)


@profile_app.command("add")
def profile_add(
    name: Annotated[str, typer.Argument(help="Profile name")],
    provider: Annotated[
        str,
        typer.Option(
            "--provider", "-p", help="Cloud provider (digitalocean, aws, static)"
        ),
    ] = "",
    region: Annotated[
        str, typer.Option("--region", "-r", help="Region/datacenter")
    ] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size/type")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
    ssh_user: Annotated[str, typer.Option("--ssh-user", help="SSH username")] = "",
    ssh_key: Annotated[str, typer.Option("--ssh-key", help="SSH key path")] = "",
    ssh_password: Annotated[
        str, typer.Option("--ssh-password", help="SSH password")
    ] = "",
    connection_type: Annotated[
        str, typer.Option("--connection", help="Connection type (ssh or winrm)")
    ] = "",
    set_default: Annotated[
        bool, typer.Option("--default", help="Set as default profile")
    ] = False,
):
    """Add or update a cloud profile."""
    console = get_console()
    from ofx.cloud.config import get_cloud_profile_manager

    mgr = get_cloud_profile_manager()
    data: dict = {}

    if provider:
        data["provider"] = provider
    if region:
        data["region"] = region
    if size:
        data["size"] = size
    if image:
        data["image"] = image
    if ssh_user:
        data["ssh_user"] = ssh_user
    if ssh_key:
        data["ssh_key"] = ssh_key
    if ssh_password:
        data["ssh_password"] = ssh_password
    if connection_type:
        data["connection_type"] = connection_type

    mgr.add(name, data)
    if set_default:
        mgr.set_default(name)

    console.print(f"[green]Profile '{name}' saved.[/green]")
    if set_default:
        console.print("[dim]Set as default profile.[/dim]")


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
):
    """Remove a cloud profile."""
    console = get_console()
    from ofx.cloud.config import get_cloud_profile_manager

    mgr = get_cloud_profile_manager()
    if not mgr.exists(name):
        console.print(f"[red]Profile '{name}' not found.[/red]")
        raise typer.Exit(code=1)

    mgr.remove(name)
    console.print(f"[green]Profile '{name}' removed.[/green]")


@profile_app.command("default")
def profile_default(
    name: Annotated[str, typer.Argument(help="Profile name to set as default")],
):
    """Set the default cloud profile."""
    console = get_console()
    from ofx.cloud.config import get_cloud_profile_manager

    mgr = get_cloud_profile_manager()
    if not mgr.exists(name):
        console.print(f"[red]Profile '{name}' not found.[/red]")
        raise typer.Exit(code=1)

    mgr.set_default(name)
    console.print(f"[green]Default profile set to '{name}'.[/green]")


@profile_app.command("show")
def profile_show(
    name: Annotated[str, typer.Argument(help="Profile name")] = "",
):
    """Show details of a cloud profile."""
    console = get_console()
    from ofx.cloud.config import get_cloud_profile_manager

    mgr = get_cloud_profile_manager()

    if not name:
        name = mgr.default_profile_name or ""
        if not name:
            console.print("[red]No default profile set. Specify a profile name.[/red]")
            raise typer.Exit(code=1)

    data = mgr.get_profile_data(name)
    if not data:
        console.print(f"[red]Profile '{name}' not found.[/red]")
        raise typer.Exit(code=1)

    import yaml
    from rich.panel import Panel
    from rich.syntax import Syntax

    yaml_str = yaml.safe_dump(data, default_flow_style=False)
    panel = Panel(
        Syntax(yaml_str, "yaml", theme="monokai"),
        title=f"Profile: {name}",
        border_style="cyan",
    )
    console.print(panel)


# ---------------------------------------------------------------------------
# Instance management
# ---------------------------------------------------------------------------

instance_app = typer.Typer(no_args_is_help=True, help="Manage cloud instances")
app.add_typer(instance_app, name="instance")


@instance_app.command("list")
def instance_list(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List cloud instances."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if not data:
            print_error(
                "Profile not found",
                f"Profile '{profile}' not found.",
            )
            raise typer.Exit(code=1)
        provider = data.get("provider", provider)

    if not provider:
        print_error(
            "Missing provider",
            "Specify --provider or --profile.",
            details="Example: ofx cloud instance list --profile default-cloud",
        )
        raise typer.Exit(code=1)

    try:
        cloud = CloudProviderRegistry.create(provider)
        instances = asyncio.run(cloud.list_instances())
    except Exception as e:
        print_error(
            "List instances failed",
            "Error while listing cloud instances.",
            details=str(e),
        )
        raise typer.Exit(code=1) from e

    if not instances:
        print_warning(
            "Instances",
            "No instances found for this provider/profile.",
        )
        return

    table = Table(title=f"Instances ({provider})")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("IP")
    table.add_column("Status")
    table.add_column("Region")
    table.add_column("Size")

    for inst in instances:
        status_style = "green" if inst.is_ready else "yellow"
        table.add_row(
            inst.instance_id,
            inst.name or "",
            inst.ip or "",
            f"[{status_style}]{inst.status}[/{status_style}]",
            inst.region or "",
            inst.size or "",
        )

    console.print(table)


@instance_app.command("destroy")
def instance_destroy(
    instance_id: Annotated[str, typer.Argument(help="Instance ID to destroy")],
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Destroy a cloud instance."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if not data:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            raise typer.Exit(code=1)
        provider = data.get("provider", provider)

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"Destroy instance {instance_id}?")
        if not confirm:
            raise typer.Abort()

    try:
        cloud = CloudProviderRegistry.create(provider)
        asyncio.run(cloud.destroy_instance(instance_id))
        console.print(f"[green]Instance {instance_id} destroyed.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e


@instance_app.command("create")
def instance_create(
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    name: Annotated[
        str, typer.Option("--name", "-n", help="Instance name")
    ] = "ofx-manual",
    region: Annotated[str, typer.Option("--region", "-r", help="Region")] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
    wait: Annotated[
        bool, typer.Option("--wait/--no-wait", help="Wait until ready")
    ] = True,
):
    """Create a cloud instance manually."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        cfg = mgr.as_cloud_config(profile)
        if not cfg:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            raise typer.Exit(code=1)
        provider = provider or cfg.provider or ""
        region = region or cfg.region or ""
        size = size or cfg.size or ""
        image = image or cfg.image or ""

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    from ofx.models.cloud import CloudConfig

    cfg = CloudConfig(
        provider=provider,
        region=region,
        size=size,
        image=image,
    )

    async def _create():
        cloud = CloudProviderRegistry.create(provider)
        inst = await cloud.create_instance(cfg)
        if wait:
            console.print(
                f"[dim]Waiting for instance '{inst.name}'[{inst.instance_id}]...[/dim]"
            )
            await cloud.wait_until_ready(inst.instance_id)
            inst = await cloud.get_instance(inst.instance_id) or inst
        return inst

    with console.status("Creating instance..."):
        try:
            instance = asyncio.run(_create())
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1) from e

    console.print("[green]Instance created:[/green]")
    console.print(f"  ID:     {instance.instance_id}")
    console.print(f"  IP:     {instance.ip or 'pending'}")
    console.print(f"  Status: {instance.status}")
    console.print(f"  Region: {instance.region}")


# ---------------------------------------------------------------------------
# Image / Snapshot management
# ---------------------------------------------------------------------------

image_app = typer.Typer(no_args_is_help=True, help="Manage cloud images/snapshots")
app.add_typer(image_app, name="image")


@image_app.command("list")
def image_list(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List available images/snapshots."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if not data:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            raise typer.Exit(code=1)
        provider = data.get("provider", provider)

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    try:
        cloud = CloudProviderRegistry.create(provider)
        snapshots = asyncio.run(cloud.list_snapshots())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e

    if not snapshots:
        console.print("[dim]No snapshots found.[/dim]")
        return

    table = Table(title=f"Snapshots ({provider})")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Size (GB)")
    table.add_column("Status")
    table.add_column("Created")

    for snap in snapshots:
        table.add_row(
            snap.snapshot_id,
            snap.name or "",
            f"{snap.size_gb:.1f}" if snap.size_gb else "",
            snap.status or "",
            (snap.created_at or datetime.now()).strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@image_app.command("create")
def image_create(
    instance_id: Annotated[str, typer.Argument(help="Instance ID to snapshot")],
    name: Annotated[str, typer.Option("--name", "-n", help="Snapshot name")] = "",
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """Create a snapshot/image from an instance."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if not data:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            raise typer.Exit(code=1)
        provider = data.get("provider", provider)

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    snapshot_name = name or f"ofx-snapshot-{instance_id[:8]}"

    with console.status(f"Creating snapshot '{snapshot_name}'..."):
        try:
            cloud = CloudProviderRegistry.create(provider)
            snapshot = asyncio.run(cloud.create_snapshot(instance_id, snapshot_name))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1) from e

    console.print("[green]Snapshot created:[/green]")
    console.print(f"  ID:   {snapshot.snapshot_id}")
    console.print(f"  Name: {snapshot.name}")


@image_app.command("delete")
def image_delete(
    snapshot_id: Annotated[str, typer.Argument(help="Snapshot ID to delete")],
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Delete a snapshot/image."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if not data:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            raise typer.Exit(code=1)
        provider = data.get("provider", provider)

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"Delete snapshot {snapshot_id}?")
        if not confirm:
            raise typer.Abort()

    try:
        cloud = CloudProviderRegistry.create(provider)
        asyncio.run(cloud.delete_snapshot(snapshot_id))
        console.print(f"[green]Snapshot {snapshot_id} deleted.[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e


# ---------------------------------------------------------------------------
# Fleet management
# ---------------------------------------------------------------------------

fleet_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud fleet (multiple instances)"
)
app.add_typer(fleet_app, name="fleet")


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

    from ofx.cloud.fleet_distributor import FleetDistributor
    from ofx.cloud.fleet_input import FleetInputParser
    from ofx.cloud.sessions import SessionManager, SessionTarget
    from ofx.commands import get_cli_env_vars
    from ofx.utils.args import parse_key_value_pairs

    if inputs is None:
        inputs = []

    parsed_inputs: dict = parse_key_value_pairs(inputs)
    parsed_env: dict = get_cli_env_vars()

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

    distributor = FleetDistributor()
    if target_list:
        chunk_files = distributor.distribute(target_list, count, distribution)
        effective_count = len(chunk_files)
    else:
        chunk_files = []
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
            if chunk_files and i < len(chunk_files):
                instance_inputs[target_var] = str(chunk_files[i])

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
        sessions = asyncio.run(_submit_fleet())

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
        console.print(
            f"[red]No sessions found for fleet group '{fleet_group_id}'[/red]"
        )
        raise typer.Exit(code=1)

    if refresh:
        mgr = SessionManager(store=store)

        async def _refresh():
            refreshed = []
            for s in sessions:
                try:
                    refreshed.append(await mgr.status(s.id))
                except Exception:
                    refreshed.append(s)
            return refreshed

        with console.status("Refreshing session statuses..."):
            sessions = asyncio.run(_refresh())

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
        status_style = _fleet_status_style(s.status.value)
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
        console.print(
            f"[red]No sessions found for fleet group '{fleet_group_id}'[/red]"
        )
        raise typer.Exit(code=1)

    # Refresh statuses first
    mgr = SessionManager(store=store)

    async def _refresh_and_fetch():
        refreshed = []
        for s in sessions:
            try:
                refreshed.append(await mgr.status(s.id))
            except Exception:
                refreshed.append(s)
        return refreshed

    with console.status("Checking fleet session statuses..."):
        sessions = asyncio.run(_refresh_and_fetch())

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
        console.print(
            f"[red]No sessions found for fleet group '{fleet_group_id}'[/red]"
        )
        raise typer.Exit(code=1)

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
    from ofx.cloud import CloudProviderRegistry
    from ofx.cloud.config import get_cloud_profile_manager

    if profile:
        mgr = get_cloud_profile_manager()
        data = mgr.get_profile_data(profile)
        if data:
            provider = data.get("provider", provider)

    if not provider:
        console.print("[red]Specify --provider or --profile[/red]")
        raise typer.Exit(code=1)

    cloud = CloudProviderRegistry.create(provider)

    try:
        all_instances = asyncio.run(cloud.list_instances())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e

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


# ---------------------------------------------------------------------------
# Quick connectivity test
# ---------------------------------------------------------------------------


@app.command("test")
def cloud_test(
    host: Annotated[str, typer.Argument(help="Host to test connectivity")],
    port: Annotated[int, typer.Option("--port", "-p", help="Port to test")] = 22,
    connection: Annotated[
        str, typer.Option("--connection", "-c", help="Connection type (ssh/winrm)")
    ] = "ssh",
    timeout: Annotated[
        int, typer.Option("--timeout", "-t", help="Timeout in seconds")
    ] = 30,
):
    """Test connectivity to a remote host."""
    console = get_console()
    from ofx.cloud.ssh import wait_for_connectivity

    with console.status(f"Testing {connection} to {host}:{port}..."):
        try:
            asyncio.run(
                wait_for_connectivity(
                    host=host,
                    os_type="windows" if connection == "winrm" else "linux",
                    ssh_port=port if connection == "ssh" else 22,
                    winrm_port=port if connection == "winrm" else 5985,
                    timeout=timeout,
                )
            )
            console.print(
                f"[green]Connection successful: {host}:{port} ({connection})[/green]"
            )
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            raise typer.Exit(code=1) from e


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------


@app.command("providers")
def list_providers():
    """List available cloud providers."""
    console = get_console()
    from ofx.cloud import CloudProviderRegistry

    providers = CloudProviderRegistry.list_providers()
    if not providers:
        console.print("[dim]No providers registered.[/dim]")
        return

    table = Table(title="Available Cloud Providers")
    table.add_column("Name", style="cyan")
    table.add_column("Class")

    for name in sorted(providers):
        cls = CloudProviderRegistry.get(name)
        cls_name = cls.__name__ if cls else "?"
        table.add_row(name, cls_name)

    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fleet_status_style(status: str) -> str:
    """Rich markup style for a session status in fleet tables."""
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
