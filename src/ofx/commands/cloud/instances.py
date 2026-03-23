"""Cloud instance management commands."""

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.cloud.helpers import resolve_provider
from ofx.commands.ui_helpers import print_error, print_warning
from ofx.settings import get_console

instance_app = typer.Typer(no_args_is_help=True, help="Manage cloud instances")


@instance_app.command("list")
def instance_list(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List cloud instances."""
    console = get_console()
    provider = resolve_provider(profile, provider)

    from ofx.cloud import CloudProviderRegistry

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
    provider = resolve_provider(profile, provider)

    if not force:
        confirm = typer.confirm(f"Destroy instance {instance_id}?")
        if not confirm:
            raise typer.Abort()

    from ofx.cloud import CloudProviderRegistry

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
