"""ASM config commands — configure server URL and API token."""

from typing import Annotated

import typer

from ofx.settings import get_console

config_app = typer.Typer(no_args_is_help=True, help="Configure ASM connection")


@config_app.command("show")
def config_show():
    """Show current ASM configuration."""
    console = get_console()
    from ofx.asm.config import get_asm_config

    cfg = get_asm_config()
    data = cfg.to_dict()

    if not data:
        console.print("[dim]ASM not configured.[/dim]")
        console.print("Run: [bold]ofx asm config set --url <URL> --token <TOKEN>[/bold]")
        return

    import yaml
    from rich.panel import Panel
    from rich.syntax import Syntax

    # Mask the token
    display = dict(data)
    if display.get("token"):
        tok = display["token"]
        display["token"] = tok[:8] + "..." + tok[-4:] if len(tok) > 12 else "***"

    yaml_str = yaml.safe_dump(display, default_flow_style=False)
    panel = Panel(
        Syntax(yaml_str, "yaml", theme="monokai"),
        title="ASM Configuration",
        border_style="cyan",
    )
    console.print(panel)


@config_app.command("set")
def config_set(
    url: Annotated[str, typer.Option("--url", "-u", help="ASM server URL (e.g. http://localhost:8080)")] = "",
    token: Annotated[str, typer.Option("--token", "-t", help="API token for authentication")] = "",
    default_scope: Annotated[str, typer.Option("--default-scope", "-s", help="Default scope ID or name")] = "",
):
    """Set ASM connection parameters.

    At minimum, --url and --token are required for the first setup.
    """
    console = get_console()
    from ofx.asm.config import get_asm_config

    cfg = get_asm_config()
    changed = False

    if url:
        cfg.url = url
        console.print(f"[green]✓ URL set to {url}[/green]")
        changed = True
    if token:
        cfg.token = token
        console.print(f"[green]✓ Token set ({token[:8]}...)[/green]")
        changed = True
    if default_scope:
        cfg.default_scope = default_scope
        console.print(f"[green]✓ Default scope set to {default_scope}[/green]")
        changed = True

    if not changed:
        console.print("[yellow]No changes. Use --url, --token, or --default-scope.[/yellow]")
        return

    # Test connectivity if we have both url and token
    if cfg.configured:
        from ofx.asm.client import ASMClient

        client = ASMClient(base_url=cfg.url, api_token=cfg.token)
        if client.health():
            console.print("[green]✓ Connection to ASM server verified.[/green]")
        else:
            console.print("[yellow]⚠ Could not reach ASM server. Check URL and token.[/yellow]")
        client.close()


@config_app.command("test")
def config_test():
    """Test connectivity to the configured ASM server."""
    console = get_console()
    from ofx.asm.config import get_asm_config

    cfg = get_asm_config()
    if not cfg.configured:
        console.print("[red]ASM not configured. Run: ofx asm config set --url <URL> --token <TOKEN>[/red]")
        raise typer.Exit(code=1)

    from ofx.asm.client import ASMClient

    client = ASMClient(base_url=cfg.url, api_token=cfg.token)
    try:
        if client.health():
            console.print(f"[green]✓ ASM server at {cfg.url} is healthy.[/green]")
            # Try listing scopes as a deeper check
            scopes = client.list_scopes()
            console.print(f"[green]✓ Authenticated. {len(scopes)} scope(s) accessible.[/green]")
        else:
            console.print(f"[red]✗ Cannot reach ASM server at {cfg.url}[/red]")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]✗ Connection failed: {e}[/red]")
        raise typer.Exit(code=1) from e
    finally:
        client.close()
