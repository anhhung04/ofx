import json
import logging
from pathlib import Path
from typing import Annotated, Any

import typer

from ofx.commands.secret.helpers import (
    _format_secret_value,
    _get_secret_type,
    _maybe_backup_store,
    _resolve_secret_input,
)
from ofx.commands.ui_helpers import (
    print_error,
    print_info,
    print_success,
    print_warning,
)
from ofx.settings import get_console, settings
from ofx.utils import secrets as secrets_store

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
logger = logging.getLogger(settings.app_branding)


def _build_secrets_table(
    secrets: dict[str, Any],
    *,
    title: str,
    show_values: bool,
):
    """Build a consistent secrets listing table."""
    from rich.table import Table

    table = Table(
        title=title,
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Type", style="magenta")
    if show_values:
        table.add_column("Value", style="red", max_width=50)

    for name in sorted(secrets.keys()):
        value = secrets[name]
        value_type = _get_secret_type(value)
        if show_values:
            table.add_row(name, value_type, _format_secret_value(value))
        else:
            table.add_row(name, value_type)
    return table


@app.command("set")
def set_secret(
    name: Annotated[str, typer.Argument(help="Secret name")],
    value: Annotated[
        str | None,
        typer.Option(
            "--value",
            "-v",
            help="Secret value (if not provided, will prompt)",
        ),
    ] = None,
    file: Annotated[
        str,
        typer.Option(
            "--file",
            "-f",
            help="Read secret value from file",
        ),
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite existing secret without prompt",
        ),
    ] = False,
):
    """Store a secret value in encrypted storage.

    The secret can be provided directly via --value, read from a file via --file,
    or entered interactively if neither option is provided. JSON values are
    automatically detected and stored as structured data.
    """
    file_path = Path(file) if file else None
    secret_value = _resolve_secret_input(name, value, file_path)
    if secrets_store.secret_exists(name) and not force:
        if not typer.confirm(f"Secret '{name}' exists. Overwrite?"):
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    try:
        secret_value = json.loads(secret_value)
    except json.JSONDecodeError:
        pass

    secrets_store.set_secret(name, secret_value)

    print_success(
        "Secret Saved",
        f"Secret '{name}' saved successfully",
        details={"Location": "Encrypted vault"},
    )


@app.command("get")
def get_secret(
    name: Annotated[str, typer.Argument(help="Secret name")],
    show: Annotated[
        bool,
        typer.Option("--show", "-s", help="Show the secret value"),
    ] = False,
):
    """Retrieve a secret value from encrypted storage.

    By default, only confirms the secret exists without displaying its value.
    Use --show to display the actual secret value. JSON secrets are displayed
    in formatted output.
    """
    value = secrets_store.get_secret(name)

    if value is None:
        print_error(
            "Secret Not Found",
            f"Secret '{name}' not found",
            details="Use 'ofx secret list' to see available secrets",
        )
        raise typer.Exit(code=1)

    if show:
        console = get_console()
        if isinstance(value, (dict, list)):
            console.print(
                f"[bold cyan]Secret: {name}[/bold cyan]\n{json.dumps(value, indent=2)}"
            )
        else:
            console.print(f"[bold cyan]Secret: {name}[/bold cyan]\n[cyan]{value}[/cyan]")
    else:
        print_info(
            "Secret Found",
            f"Secret '{name}' exists in encrypted store",
            details={"Hint": "Use --show to display the value"},
        )


@app.command("list")
def list_secrets(
    filter_type: Annotated[
        str,
        typer.Option(
            "--filter",
            "-f",
            help="Filter by type (string, json, api-key, password, token)",
        ),
    ] = "",
    search: Annotated[
        str,
        typer.Option(
            "--search",
            "-s",
            help="Search in secret names",
        ),
    ] = "",
    show_values: Annotated[
        bool,
        typer.Option(
            "--show-values",
            help="Show secret values (WARNING: displays sensitive data)",
        ),
    ] = False,
):
    """List all stored secrets with optional filtering and searching.

    Displays secrets in a table format with name and type information.
    Supports filtering by secret type and searching within secret names.
    Use --show-values with caution as it displays sensitive data.
    """
    console = get_console()
    secrets = secrets_store.list_secrets()

    if not secrets:
        typer.secho("No secrets found", fg=typer.colors.YELLOW)
        return

    filtered_secrets: dict[str, Any] = {}
    for name, value in secrets.items():
        if search and search.lower() not in name.lower():
            continue

        if filter_type:
            secret_type = _get_secret_type(value)
            if secret_type != filter_type.lower():
                continue

        filtered_secrets[name] = value

    if not filtered_secrets:
        print_warning(
            "Search Results",
            "No secrets match the specified filters",
            hint="Try different search criteria",
        )
        return

    console.print(
        _build_secrets_table(
            filtered_secrets,
            title=f"[*] Stored Secrets ({len(filtered_secrets)} found)",
            show_values=show_values,
        )
    )

    if show_values:
        typer.secho(
            "\n⚠️ WARNING: Secret values are displayed above!",
            fg=typer.colors.YELLOW,
            bold=True,
        )


@app.command("search")
def search_secrets(
    pattern: Annotated[
        str, typer.Argument(help="Search pattern (supports wildcards: * and ?)")
    ],
    show_values: Annotated[
        bool,
        typer.Option(
            "--show-values",
            help="Show secret values (WARNING: displays sensitive data)",
        ),
    ] = False,
):
    """Search for secrets by name pattern with wildcard support.

    Supports Unix shell-style wildcards: * matches any sequence of characters,
    ? matches any single character. Search is case-insensitive.
    Use --show-values with caution as it displays sensitive data.
    """
    import fnmatch

    console = get_console()
    secrets = secrets_store.list_secrets()

    if not secrets:
        print_warning(
            "Secrets",
            "No secrets found in encrypted store",
            hint="Use 'ofx secret set <name>' to add secrets",
        )
        return

    matches: dict[str, Any] = {}

    for name, value in secrets.items():
        if fnmatch.fnmatch(name.lower(), pattern.lower()):
            matches[name] = value

    if not matches:
        print_warning(
            "Search Results",
            f"No secrets match pattern: {pattern}",
            hint="Try a different search pattern",
        )
        return

    console.print(
        _build_secrets_table(
            matches,
            title=f"🔍 Search Results for '{pattern}' ({len(matches)} found)",
            show_values=show_values,
        )
    )

    if show_values:
        typer.secho(
            "\n⚠️ WARNING: Secret values are displayed above!",
            fg=typer.colors.YELLOW,
            bold=True,
        )


@app.command("delete")
def delete_secret(
    name: Annotated[str, typer.Argument(help="Secret name")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup before deletion (path to .enc file)",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite backup file if it exists",
        ),
    ] = False,
):
    """Delete a secret from encrypted storage.

    Permanently removes a secret by name. Requires confirmation unless
    --force is used. This action cannot be undone.
    """
    if not secrets_store.secret_exists(name):
        typer.secho(f"❌ Secret '{name}' not found", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    _maybe_backup_store(backup_to, None, backup_overwrite)

    if not force:
        confirm = typer.confirm(f"Delete secret '{name}'?")
        if not confirm:
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    secrets_store.delete_secret(name)

    print_success(
        "Deleted",
        f"Secret '{name}' deleted successfully",
        details={"Location": "Encrypted store"},
    )


@app.command("export")
def export_secrets(
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output file path",
        ),
    ] = "secrets_export.json",
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup before export (path to .enc file)",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite backup file if it exists",
        ),
    ] = False,
):
    """Export secrets to a file for backup or migration.

    Creates an unencrypted JSON file containing all secrets. Keep the exported
    file secure as it contains sensitive data. Use the backup command for
    encrypted backups instead.
    """
    path_output = Path(output)
    _maybe_backup_store(backup_to, None, backup_overwrite)

    count = secrets_store.export_secrets(path_output)

    if not count:
        print_warning(
            "Export",
            "No secrets to export",
        )
        raise typer.Exit()

    print_success(
        "Export Complete",
        f"Exported {count} secrets successfully",
        details={"File": output},
    )
    print_warning(
        "Security Warning",
        "Exported file contains unencrypted secrets!",
        hint="Keep this file secure.",
    )


@app.command("import")
def import_secrets(
    file: Annotated[Path, typer.Argument(..., help="JSON file containing secrets")],
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Overwrite existing secrets"),
    ] = False,
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup before import (path to .enc file)",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite backup file if it exists",
        ),
    ] = False,
):
    """Import secrets from a JSON file.

    Reads secrets from an unencrypted JSON file and stores them in encrypted
    storage. By default, skips existing secrets unless --overwrite is used.
    """

    try:
        _maybe_backup_store(backup_to, None, backup_overwrite)
        imported = secrets_store.import_secrets_from_file(file, overwrite)
    except FileNotFoundError as e:
        print_error(
            "Import Error",
            "File not found",
            details=str(e),
        )
        raise typer.Exit(code=1) from e
    except ValueError as e:
        print_error(
            "Import Error",
            "Invalid file format",
            details=str(e),
        )
        raise typer.Exit(code=1) from e

    print_success(
        "Import Complete",
        f"Imported {imported} secrets successfully",
        details={"File": str(file)},
    )


@app.command("clear")
def clear_secrets(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup before clearing (path to .enc file)",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite backup file if it exists",
        ),
    ] = False,
):
    """Clear all secrets from encrypted storage.

    Permanently removes ALL secrets from the store. Requires confirmation
    unless --force is used. This action cannot be undone.
    """

    secrets = secrets_store.list_secrets()

    if not secrets:
        print_warning(
            "Secrets",
            "No secrets to clear",
        )
        return

    _maybe_backup_store(backup_to, None, backup_overwrite)

    if not force:
        print_warning(
            "Warning",
            f"This will permanently delete ALL {len(secrets)} secrets!",
            "This action cannot be undone.",
        )
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            get_console().print("[yellow]Operation cancelled[/yellow]")
            raise typer.Exit()

    secrets_store.clear_secrets()
    print_success("Cleared", f"All {len(secrets)} secrets cleared successfully")


@app.command("store")
def show_store_location():
    """Display the path to the secret store file.

    Shows the location of the encrypted secrets file and basic information
    about the store. Useful for backup operations or troubleshooting.
    """
    info = secrets_store.get_store_info()

    typer.secho(f"Secret store: {info['path']}", fg=typer.colors.CYAN)
    typer.secho(
        "Set OFX_SECRETS_STORE environment variable to change location",
        fg=typer.colors.YELLOW,
        dim=True,
    )

    if info["exists"]:
        typer.secho(f"Store size: {info['size']} bytes", fg=typer.colors.CYAN)
        typer.secho(f"Secret count: {info['count']}", fg=typer.colors.CYAN)

