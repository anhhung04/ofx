"""Cloud image / snapshot management commands."""

import asyncio
from datetime import datetime
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.cloud.helpers import create_cloud_provider, run_cloud_sync
from ofx.settings import get_console

image_app = typer.Typer(no_args_is_help=True, help="Manage cloud images/snapshots")


@image_app.command("list")
def image_list(
    provider: Annotated[
        str, typer.Option("--provider", "-p", help="Cloud provider")
    ] = "",
    profile: Annotated[str, typer.Option("--profile", help="Use a cloud profile")] = "",
):
    """List available images/snapshots."""
    console = get_console()
    provider, cloud = create_cloud_provider(profile, provider)
    snapshots = run_cloud_sync(
        "list snapshots", lambda: asyncio.run(cloud.list_snapshots())
    )

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
    provider, cloud = create_cloud_provider(profile, provider)

    snapshot_name = name or f"ofx-snapshot-{instance_id[:8]}"

    with console.status(f"Creating snapshot '{snapshot_name}'..."):
        snapshot = run_cloud_sync(
            "create snapshot",
            lambda: asyncio.run(cloud.create_snapshot(instance_id, snapshot_name)),
        )

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
    _, cloud = create_cloud_provider(profile, provider)

    if not force:
        confirm = typer.confirm(f"Delete snapshot {snapshot_id}?")
        if not confirm:
            raise typer.Abort()

    run_cloud_sync(
        "delete snapshot", lambda: asyncio.run(cloud.delete_snapshot(snapshot_id))
    )
    console.print(f"[green]Snapshot {snapshot_id} deleted.[/green]")
