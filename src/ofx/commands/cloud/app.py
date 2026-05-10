"""Cloud management CLI commands for OFX.

Provides commands to manage cloud profiles, instances, and images.
"""

import asyncio
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.cloud.fleets import fleet_app
from ofx.commands.cloud.images import image_app
from ofx.commands.cloud.instances import instance_app
from ofx.commands.cloud.profiles import profile_app
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "cloud"
HELP = "Manage cloud profiles, instances, and images"

app.add_typer(profile_app, name="profile")
app.add_typer(instance_app, name="instance")
app.add_typer(image_app, name="image")
app.add_typer(fleet_app, name="fleet")


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
        except (TimeoutError, OSError) as e:
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
