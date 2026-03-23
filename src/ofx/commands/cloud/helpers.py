"""Shared helpers for cloud CLI commands."""

import typer


def resolve_provider(profile: str = "", provider: str = "") -> str:
    """Resolve a cloud provider name from a profile or explicit --provider flag.

    Exits with code 1 if no provider can be determined.
    """
    from ofx.cloud.config import get_cloud_profile_manager
    from ofx.settings import get_console

    console = get_console()

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

    return provider
