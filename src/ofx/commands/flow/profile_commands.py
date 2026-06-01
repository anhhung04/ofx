"""CLI commands for managing OFX execution profiles."""

from __future__ import annotations

from contextlib import suppress
from typing import Annotated

import typer
from rich.table import Table

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

get_profile_manager = None
get_console = None


def _get_profile_deps():
    profile_manager_getter = get_profile_manager
    if profile_manager_getter is None:
        from ofx.profiles.manager import get_profile_manager as profile_manager_getter

    console_getter = get_console
    if console_getter is None:
        from ofx.settings import get_console as console_getter

    return console_getter(), profile_manager_getter()


def _run_profile_mutation(action, success_message: str) -> None:
    console, mgr = _get_profile_deps()
    try:
        action(mgr)
        console.print(success_message)
    except KeyError as e:
        _profile_error(console, e)


def _fail_invalid_set_syntax(console, item: str) -> None:
    console.print(f"[error]Invalid format '{item}', use key=value[/error]")
    raise typer.Exit(1)


def _print_no_profiles_hint(console) -> None:
    console.print("[dim]No profiles configured. Add one with:[/dim]")
    console.print("  ofx flow profile add <name> --set rate_limit=30")


def _profile_error(console, error: Exception) -> None:
    console.print(f"[error]{error}[/error]")
    raise typer.Exit(1) from None


def _parse_profile_set_value(value: str) -> object:
    value = value.strip()
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False

    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1]
                return [v.strip() for v in inner.split(",") if v.strip()]
            return value


def _apply_profile_set_value(console, data: dict, item: str) -> None:
    if "=" not in item:
        _fail_invalid_set_syntax(console, item)

    key, raw_value = item.split("=", 1)
    parsed_value = _parse_profile_set_value(raw_value)

    keys = key.strip().split(".")
    current = data
    for part in keys[:-1]:
        current = current.setdefault(part, {})
    current[keys[-1]] = parsed_value


@app.command("list")
def list_profiles():
    """List all configured profiles."""
    console, mgr = _get_profile_deps()
    names = mgr.list_profiles()

    if not names:
        _print_no_profiles_hint(console)
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

    console, mgr = _get_profile_deps()

    try:
        data = mgr.get_profile_data(name)
    except KeyError as e:
        _profile_error(console, e)

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
        list[str] | None,
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
    console, mgr = _get_profile_deps()

    data: dict = {}
    if description:
        data["description"] = description

    for item in set_values or []:
        _apply_profile_set_value(console, data, item)

    def _save_profile(manager):
        manager.add(name, data)
        if default:
            manager.set_default(name)

    _run_profile_mutation(
        _save_profile,
        f"[success]Profile '{name}' saved[/success]",
    )


@app.command("remove")
def remove_profile(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
):
    """Remove a profile."""
    _run_profile_mutation(
        lambda mgr: mgr.remove(name),
        f"[success]Profile '{name}' removed[/success]",
    )


@app.command("default")
def set_default(
    name: Annotated[str, typer.Argument(help="Profile name to set as default")],
):
    """Set the default profile."""
    _run_profile_mutation(
        lambda mgr: mgr.set_default(name),
        f"[success]Default profile set to '{name}'[/success]",
    )
