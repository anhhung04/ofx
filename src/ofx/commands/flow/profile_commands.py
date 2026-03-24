"""CLI commands for managing OFX execution profiles."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command("list")
def list_profiles():
    """List all configured profiles."""
    from ofx.profiles.manager import get_profile_manager
    from ofx.settings import get_console

    console = get_console()
    mgr = get_profile_manager()
    names = mgr.list_profiles()

    if not names:
        console.print("[dim]No profiles configured. Add one with:[/dim]")
        console.print("  ofx flow profile add <name> --set rate_limit=30")
        return

    default = mgr.default_profile_name
    table = Table(title="Profiles", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Rate Limit")
    table.add_column("Time Window")
    table.add_column("Default", justify="center")

    for name in names:
        try:
            profile = mgr.resolve(name)
        except Exception:
            table.add_row(name, "[red]error loading[/red]", "", "", "")
            continue

        tw = profile.time_window
        tw_str = (
            f"{tw.start}–{tw.end} {tw.timezone}" if tw.enabled else "[dim]off[/dim]"
        )
        rate = str(profile.rate_limit) if profile.rate_limit else "[dim]unlimited[/dim]"
        is_default = "✓" if name == default else ""

        table.add_row(name, profile.description, rate, tw_str, is_default)

    console.print(table)


@app.command("show")
def show_profile(
    name: Annotated[str, typer.Argument(help="Profile name to inspect")],
):
    """Show detailed profile configuration."""
    import yaml
    from rich.panel import Panel
    from rich.syntax import Syntax

    from ofx.profiles.manager import get_profile_manager
    from ofx.settings import get_console

    console = get_console()
    mgr = get_profile_manager()

    try:
        data = mgr.get_profile_data(name)
    except KeyError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1) from None

    yaml_str = yaml.dump({name: data}, default_flow_style=False, sort_keys=False)
    console.print(
        Panel(
            Syntax(yaml_str, "yaml", theme="monokai"),
            title=f"Profile: {name}",
            border_style="cyan",
        )
    )


@app.command("add")
def add_profile(
    name: Annotated[str, typer.Argument(help="Profile name")],
    description: Annotated[
        str,
        typer.Option("--desc", "-d", help="Profile description"),
    ] = "",
    set_values: Annotated[
        list[str],
        typer.Option(
            "--set",
            "-s",
            help="Set profile values in key=value format (dot notation for nested, e.g. time_window.enabled=true)",
        ),
    ] = None,
    default: Annotated[
        bool,
        typer.Option("--default", help="Set as the default profile"),
    ] = False,
):
    """Add or update a profile."""
    from ofx.profiles.manager import get_profile_manager
    from ofx.settings import get_console

    console = get_console()
    mgr = get_profile_manager()

    data: dict = {}
    if description:
        data["description"] = description

    for item in set_values or []:
        if "=" not in item:
            console.print(f"[error]Invalid format '{item}', use key=value[/error]")
            raise typer.Exit(1)
        key, value = item.split("=", 1)
        _set_nested(data, key.strip(), _parse_value(value.strip()))

    mgr.add(name, data)

    if default:
        mgr.set_default(name)

    console.print(f"[success]Profile '{name}' saved[/success]")


@app.command("remove")
def remove_profile(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
):
    """Remove a profile."""
    from ofx.profiles.manager import get_profile_manager
    from ofx.settings import get_console

    console = get_console()
    mgr = get_profile_manager()

    try:
        mgr.remove(name)
        console.print(f"[success]Profile '{name}' removed[/success]")
    except KeyError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1) from None


@app.command("default")
def set_default(
    name: Annotated[str, typer.Argument(help="Profile name to set as default")],
):
    """Set the default profile."""
    from ofx.profiles.manager import get_profile_manager
    from ofx.settings import get_console

    console = get_console()
    mgr = get_profile_manager()

    try:
        mgr.set_default(name)
        console.print(f"[success]Default profile set to '{name}'[/success]")
    except KeyError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1) from None


# ── Helpers ────────────────────────────────────────────────────────


def _set_nested(data: dict, dotted_key: str, value) -> None:
    """Set a value in a nested dict using dot notation."""
    keys = dotted_key.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _parse_value(value: str):
    """Parse a string value into its appropriate Python type."""
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # Handle lists: "[a,b,c]"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return [v.strip() for v in inner.split(",") if v.strip()]
    return value
