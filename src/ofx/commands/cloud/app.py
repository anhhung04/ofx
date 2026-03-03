"""Cloud management CLI commands for OFX.

Provides commands to manage cloud profiles, instances, and images.
"""

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "cloud"
HELP = "Manage cloud profiles, instances, and images"

console = get_console()


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
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider (digitalocean, aws, static)")] = "",
    region: Annotated[str, typer.Option("--region", "-r", help="Region/datacenter")] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size/type")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
    ssh_user: Annotated[str, typer.Option("--ssh-user", help="SSH username")] = "",
    ssh_key: Annotated[str, typer.Option("--ssh-key", help="SSH key path")] = "",
    ssh_password: Annotated[str, typer.Option("--ssh-password", help="SSH password")] = "",
    connection_type: Annotated[str, typer.Option("--connection", help="Connection type (ssh or winrm)")] = "",
    set_default: Annotated[bool, typer.Option("--default", help="Set as default profile")] = False,
):
    """Add or update a cloud profile."""
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

    mgr.add(name, data, default=set_default)
    console.print(f"[green]Profile '{name}' saved.[/green]")
    if set_default:
        console.print("[dim]Set as default profile.[/dim]")


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
):
    """Remove a cloud profile."""
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

instance_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud instances"
)
app.add_typer(instance_app, name="instance")


@instance_app.command("list")
def instance_list(
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List cloud instances."""
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
        instances = asyncio.run(cloud.list_instances())
    except Exception as e:
        console.print(f"[red]Error listing instances: {e}[/red]")
        raise typer.Exit(code=1) from e

    if not instances:
        console.print("[dim]No instances found.[/dim]")
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
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
):
    """Destroy a cloud instance."""
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
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    name: Annotated[str, typer.Option("--name", "-n", help="Instance name")] = "ofx-manual",
    region: Annotated[str, typer.Option("--region", "-r", help="Region")] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
    wait: Annotated[bool, typer.Option("--wait/--no-wait", help="Wait until ready")] = True,
):
    """Create a cloud instance manually."""
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
            console.print(f"[dim]Waiting for instance {inst.instance_id}...[/dim]")
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

image_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud images/snapshots"
)
app.add_typer(image_app, name="image")


@image_app.command("list")
def image_list(
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List available images/snapshots."""
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
            snap.created_at or "",
        )

    console.print(table)


@image_app.command("create")
def image_create(
    instance_id: Annotated[str, typer.Argument(help="Instance ID to snapshot")],
    name: Annotated[str, typer.Option("--name", "-n", help="Snapshot name")] = "",
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """Create a snapshot/image from an instance."""
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
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
):
    """Delete a snapshot/image."""
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
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    name_prefix: Annotated[str, typer.Option("--prefix", help="Instance name prefix")] = "ofx-fleet",
    region: Annotated[str, typer.Option("--region", "-r", help="Region")] = "",
    size: Annotated[str, typer.Option("--size", "-s", help="Instance size")] = "",
    image: Annotated[str, typer.Option("--image", "-i", help="OS image")] = "",
):
    """Create a fleet of cloud instances."""
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


@fleet_app.command("destroy")
def fleet_destroy(
    tag: Annotated[str, typer.Option("--tag", help="Destroy instances with this tag")] = "",
    prefix: Annotated[str, typer.Option("--prefix", help="Destroy instances matching name prefix")] = "ofx-fleet",
    provider: Annotated[str, typer.Option("--provider", "-p", help="Cloud provider")] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
):
    """Destroy fleet instances by tag or name prefix."""
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
    connection: Annotated[str, typer.Option("--connection", "-c", help="Connection type (ssh/winrm)")] = "ssh",
    timeout: Annotated[int, typer.Option("--timeout", "-t", help="Timeout in seconds")] = 30,
):
    """Test connectivity to a remote host."""
    from ofx.cloud.ssh import wait_for_connectivity

    with console.status(f"Testing {connection} to {host}:{port}..."):
        try:
            asyncio.run(wait_for_connectivity(
                host=host,
                os_type="windows" if connection == "winrm" else "linux",
                ssh_port=port if connection == "ssh" else 22,
                winrm_port=port if connection == "winrm" else 5985,
                timeout=timeout,
            ))
            console.print(f"[green]Connection successful: {host}:{port} ({connection})[/green]")
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            raise typer.Exit(code=1) from e


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------

@app.command("providers")
def list_providers():
    """List available cloud providers."""
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
