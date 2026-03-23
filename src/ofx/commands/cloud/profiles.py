"""Cloud profile management commands."""

from typing import Annotated

import typer
from rich.table import Table

from ofx.settings import get_console

profile_app = typer.Typer(
    no_args_is_help=True, help="Manage cloud configuration profiles"
)


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
