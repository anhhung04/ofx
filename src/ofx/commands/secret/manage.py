import getpass
import json
import logging
from pathlib import Path
from typing import Any, Dict, Annotated

import typer
from rich.panel import Panel

from ofx.settings import SECRETS_DIR, settings, get_console
from ofx.utils import secrets as secrets_store

app = typer.Typer()
logger = logging.getLogger(settings.app_branding)


def _resolve_secret_input(name: str, value: str | None, file: Path | None) -> str:
    """Resolve a secret value from CLI options or interactive prompt.

    - Prevents using --value and --file together.
    - Validates file existence when provided.
    - Prompts interactively if neither option is supplied.
    """
    if value is not None and file is not None:
        typer.secho("❌ Use either --value or --file, not both", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if file is not None:
        if not file.exists():
            typer.secho(f"❌ File not found: {file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        return file.read_text().strip()

    if value is not None:
        return value

    return getpass.getpass(f"Enter value for secret '{name}': ")


def _resolve_passphrase(passphrase: str, ask: bool) -> str | None:
    """Return the passphrase from flag or prompt; prompt wins when requested."""
    if ask:
        return getpass.getpass("Enter passphrase: ")
    return passphrase if passphrase else None


def _maybe_backup_store(
    backup_path: str, passphrase: str | None, overwrite: bool
) -> None:
    """Create a backup if requested, failing fast on overwrite collisions."""
    if not backup_path:
        return

    backup_path_obj = Path(backup_path)
    if backup_path_obj.exists() and not overwrite:
        typer.secho(
            f"❌ Backup file already exists: {backup_path_obj}. Use --backup-overwrite to replace",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    count = secrets_store.backup_secrets(backup_path_obj, passphrase=passphrase)

    if count == 0:
        typer.secho("No secrets to backup; skipping backup creation", fg=typer.colors.YELLOW)
        return

    typer.secho(
        f"💾 Backup created at {backup_path_obj} ({count} secrets)",
        fg=typer.colors.CYAN,
    )


@app.command("set")
def set_secret(
    name: Annotated[str, typer.Argument(help="Secret name")],
    value: Annotated[
        str,
        typer.Option(
            "--value",
            "-v",
            help="Secret value (if not provided, will prompt)",
        ),
    ],
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
            "-f",
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
    
    console.print(Panel(
        f"[bold green]Secret '{name}' saved successfully[/bold green]\n"
        "[dim]Stored in encrypted vault[/dim]",
        title="[bold green][OK] Secret Saved[/bold green]",
        border_style="green"
    ))


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
        console.print(Panel(
            f"[bold red]Secret '{name}' not found[/bold red]\n"
            "[dim]Use 'ofx secret list' to see available secrets[/dim]",
            title="[X] Not Found",
            border_style="red"
        ))
        raise typer.Exit(code=1)

    if show:
        if isinstance(value, (dict, list)):
            console.print(Panel(
                json.dumps(value, indent=2),
                title=f"[*] Secret: {name}",
                border_style="cyan"
            ))
        else:
            console.print(Panel(
                f"[cyan]{value}[/cyan]",
                title=f"[*] Secret: {name}",
                border_style="cyan"
            ))
    else:
        console.print(Panel(
            f"[green]Secret '{name}' exists in encrypted store[/green]\n"
            "[dim]Use --show to display the value[/dim]",
            title="[OK] Secret Found",
            border_style="green"
        ))


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
    from rich.table import Table

    secrets = secrets_store.list_secrets()

    if not secrets:
        typer.secho("No secrets found", fg=typer.colors.YELLOW)
        return

    filtered_secrets: Dict[str, Any] = {}
    for name, value in secrets.items():
        if search and search.lower() not in name.lower():
            continue

        if filter_type:
            secret_type = _get_secret_type(value)
            if secret_type != filter_type.lower():
                continue

        filtered_secrets[name] = value

    if not filtered_secrets:
        console.print(Panel(
            "[yellow]No secrets match the specified filters[/yellow]\n"
            "[dim]Try different search criteria[/dim]",
            title="[?] Search Results",
            border_style="yellow"
        ))
        return

    table = Table(
        title=f"[*] Stored Secrets ({len(filtered_secrets)} found)",
        border_style="cyan",
        header_style="bold cyan"
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Type", style="magenta")
    if show_values:
        table.add_column("Value", style="red", max_width=50)

    for name in sorted(filtered_secrets.keys()):
        value = filtered_secrets[name]
        value_type = _get_secret_type(value)

        if show_values:
            value_display = _format_secret_value(value)
            table.add_row(name, value_type, value_display)
        else:
            table.add_row(name, value_type)

    console.print(table)

    if show_values:
        typer.secho(
            "\n⚠️ WARNING: Secret values are displayed above!",
            fg=typer.colors.YELLOW,
            bold=True,
        )


@app.command("search")
def search_secrets(
    pattern: Annotated[str, typer.Argument(help="Search pattern (supports wildcards: * and ?)")],
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

    from rich.table import Table

    
    secrets = secrets_store.list_secrets()

    if not secrets:
        console.print(Panel(
            "[yellow]No secrets found in encrypted store[/yellow]\n"
            "[dim]Use 'ofx secret set <name>' to add secrets[/dim]",
            title="[*] Secrets",
            border_style="yellow"
        ))
        return

    matches: Dict[str, Any] = {}

    for name, value in secrets.items():
        if fnmatch.fnmatch(name.lower(), pattern.lower()):
            matches[name] = value

    if not matches:
        console.print(Panel(
            f"[yellow]No secrets match pattern:[/yellow] [cyan]{pattern}[/cyan]\n"
            "[dim]Try a different search pattern[/dim]",
            title="🔍 Search Results",
            border_style="yellow"
        ))
        return

    table = Table(
        title=f"🔍 Search Results for '{pattern}' ({len(matches)} found)",
        border_style="cyan",
        header_style="bold cyan"
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Type", style="magenta")
    if show_values:
        table.add_column("Value", style="red", max_width=50)

    for name in sorted(matches.keys()):
        value = matches[name]
        value_type = _get_secret_type(value)

        if show_values:
            value_display = _format_secret_value(value)
            table.add_row(name, value_type, value_display)
        else:
            table.add_row(name, value_type)

    console.print(table)

    if show_values:
        typer.secho(
            "\n⚠️ WARNING: Secret values are displayed above!",
            fg=typer.colors.YELLOW,
            bold=True,
        )


def _get_secret_type(value) -> str:
    """Determine the type of a secret value"""
    if isinstance(value, dict):
        return "json"
    elif isinstance(value, list):
        return "json"
    elif isinstance(value, str):
        if len(value) > 50 and any(char in value for char in ['.', '/', '=', '+']):
            return "token"
        elif len(value) > 20 and any(char in value for char in ['@', '.']):
            return "api-key"
        elif len(value) >= 8 and any(char.isdigit() for char in value) and any(char.isupper() for char in value):
            return "password"
        else:
            return "string"
    else:
        return "unknown"


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"

    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _format_secret_value(value) -> str:
    """Format a secret value for display in tables"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=0, separators=(',', ':'))
    elif isinstance(value, str):
        if len(value) > 50:
            return value[:47] + "..."
        return value
    else:
        return str(value)


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
    
    console.print(Panel(
        f"[bold green]Secret '{name}' deleted successfully[/bold green]\n"
        "[dim]Removed from encrypted store[/dim]",
        title="[OK] Deleted",
        border_style="green"
    ))


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
        console.print(Panel(
            "[yellow]No secrets to export[/yellow]",
            title="[!] Export",
            border_style="yellow"
        ))
        raise typer.Exit()

    console.print(Panel(
        f"[bold green]Exported {count} secrets successfully[/bold green]\n"
        f"[bold]File:[/bold] [cyan]{output}[/cyan]\n\n"
        "[bold yellow][!] WARNING[/bold yellow]\n"
        "[yellow]Exported file contains unencrypted secrets!\n"
        "Keep this file secure.[/yellow]",
        title="[OK] Export Complete",
        border_style="green"
    ))


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
        console.print(Panel(
            f"[bold red]File not found[/bold red]\n"
            f"[red]{e}[/red]",
            title="[X] Import Error",
            border_style="red"
        ))
        raise typer.Exit(code=1) from e
    except ValueError as e:
        console.print(Panel(
            f"[bold red]Invalid file format[/bold red]\n"
            f"[red]{e}[/red]",
            title="[X] Import Error",
            border_style="red"
        ))
        raise typer.Exit(code=1) from e

    console.print(Panel(
        f"[bold green]Imported {imported} secrets successfully[/bold green]\n"
        f"[dim]File: {file}[/dim]",
        title="[OK] Import Complete",
        border_style="green"
    ))


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
        console.print(Panel(
            "[yellow]No secrets to clear[/yellow]",
            title="[*] Secrets",
            border_style="yellow"
        ))
        return

    _maybe_backup_store(backup_to, None, backup_overwrite)

    if not force:
        console.print(Panel(
            f"[bold red]This will permanently delete ALL {len(secrets)} secrets![/bold red]\n"
            "[yellow]This action cannot be undone.[/yellow]",
            title="[!] Warning",
            border_style="red"
        ))
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Operation cancelled[/yellow]")
            raise typer.Exit()

    secrets_store.clear_secrets()
    console.print(Panel(
        f"[bold green]All {len(secrets)} secrets cleared successfully[/bold green]",
        title="[OK] Cleared",
        border_style="green"
    ))


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


@app.command("backup")
def backup_secrets(
    output_file: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Output file path (default: auto-generated)",
        ),
    ] = "",
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing backup file"),
    ] = False,
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup of current store before writing new backup",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite pre-backup file if it exists",
        ),
    ] = False,
    passphrase: Annotated[
        str,
        typer.Option(
            "--passphrase",
            "-p",
            envvar="OFX_SECRETS_PASSPHRASE",
            help="Passphrase to unlock the secret store (env: OFX_SECRETS_PASSPHRASE)",
        ),
    ] = "",
    ask_passphrase: Annotated[
        bool,
        typer.Option("--ask-passphrase", help="Prompt for passphrase interactively"),
    ] = False,
):
    """Create an encrypted backup of all secrets with timestamp.

    Creates a timestamped, encrypted backup file containing all secrets.
    If no output file is specified, generates a filename with current timestamp.
    The backup can be restored using the restore command.
    """
    resolved_passphrase = _resolve_passphrase(passphrase, ask_passphrase)
    _maybe_backup_store(backup_to, resolved_passphrase, backup_overwrite)
    secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)

    if not secrets:
        console.print(Panel(
            "[yellow]No secrets to backup[/yellow]",
            title="[*] Backup",
            border_style="yellow"
        ))
        return

    if not output_file:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"ofx_secrets_backup_{timestamp}.enc"

    output_path = Path(output_file)
    if output_path.exists() and not force:
        console.print(Panel(
            f"[bold red]Backup file already exists:[/bold red] [cyan]{output_path}[/cyan]\n"
            "[yellow]Use --force to overwrite[/yellow]",
            title="[X] File Exists",
            border_style="red"
        ))
        raise typer.Exit(1)

    try:
        count = secrets_store.backup_secrets(output_path, passphrase=resolved_passphrase)
        
        file_size = output_path.stat().st_size
        console.print(Panel(
            f"[bold green]Backup created successfully[/bold green]\n"
            f"[bold]File:[/bold] [cyan]{output_path}[/cyan]\n"
            f"[bold]Secrets:[/bold] {count}\n"
            f"[bold]Size:[/bold] {_format_file_size(file_size)}",
            title="[OK] Backup Complete",
            border_style="green"
        ))

    except Exception as e:
        console.print(Panel(
            f"[bold red]Backup failed[/bold red]\n"
            f"[red]{e}[/red]",
            title="[X] Backup Error",
            border_style="red"
        ))
        raise typer.Exit(1) from e


@app.command("restore")
def restore_secrets(
    backup_file: Annotated[Path, typer.Argument(..., help="Backup file to restore from")],
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Overwrite existing secrets with same names",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be restored without actually doing it",
        ),
    ] = False,
    backup_to: Annotated[
        str,
        typer.Option(
            "--backup-to",
            help="Create an encrypted backup of current store before restoring",
        ),
    ] = "",
    backup_overwrite: Annotated[
        bool,
        typer.Option(
            "--backup-overwrite",
            help="Overwrite pre-backup file if it exists",
        ),
    ] = False,
    passphrase: Annotated[
        str,
        typer.Option(
            "--passphrase",
            "-p",
            envvar="OFX_SECRETS_PASSPHRASE",
            help="Passphrase to unlock the secret store (env: OFX_SECRETS_PASSPHRASE)",
        ),
    ] = "",
    ask_passphrase: Annotated[
        bool,
        typer.Option(
            "--ask-passphrase",
            help="Prompt for passphrase interactively",
        ),
    ] = False,
):
    """Restore secrets from an encrypted backup file.

    Restores secrets from a backup created with the backup command.
    Supports conflict resolution when secrets already exist.
    Use --dry-run to preview what would be restored without making changes.
    """
    from rich.table import Table

    resolved_passphrase = _resolve_passphrase(passphrase, ask_passphrase)
    if not backup_file.exists():
        console.print(Panel(
            f"[bold red]Backup file not found[/bold red]\n"
            f"[red]{backup_file}[/red]",
            title="[X] File Not Found",
            border_style="red"
        ))
        raise typer.Exit(1)

    _maybe_backup_store(backup_to, resolved_passphrase, backup_overwrite)

    try:
        info = secrets_store.get_backup_info(backup_file, passphrase=resolved_passphrase)

        console.print(Panel(
            f"[bold]File:[/bold] [cyan]{backup_file}[/cyan]\n"
            f"[bold]Created:[/bold] {info['created']}\n"
            f"[bold]Secrets:[/bold] {info['count']}\n"
            f"[bold]Size:[/bold] {_format_file_size(info['size'])}",
            title="[#] Backup Information",
            border_style="cyan"
        ))

        if dry_run:
            console.print(Panel(
                "[yellow]Dry run mode - no changes will be made[/yellow]",
                title="[?] Preview",
                border_style="yellow"
            ))
            table = Table(
                title="Secrets to be Restored",
                border_style="cyan",
                header_style="bold cyan"
            )
            table.add_column("Name", style="cyan bold")
            table.add_column("Type", style="magenta")
            table.add_column("Status", style="yellow")

            current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
            for name, value in info['secrets'].items():
                status = "New" if name not in current_secrets else ("Overwrite" if overwrite else "Skip")
                secret_type = _get_secret_type(value)
                table.add_row(name, secret_type, status)

            console.print(table)
            return

        current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
        conflicts = []
        for name in info['secrets'].keys():
            if name in current_secrets and not overwrite:
                conflicts.append(name)

        if conflicts:
            conflict_list = "\n".join([f"• {name}" for name in conflicts[:5]])
            if len(conflicts) > 5:
                conflict_list += f"\n• ... and {len(conflicts) - 5} more"
            
            console.print(Panel(
                f"[yellow]{len(conflicts)} secrets already exist and will be skipped:[/yellow]\n\n"
                f"{conflict_list}\n\n"
                "[dim]Use --overwrite to replace existing secrets[/dim]",
                title="[!] Conflicts Detected",
                border_style="yellow"
            ))

            if not typer.confirm("Continue with restore?"):
                console.print("[yellow]Operation cancelled[/yellow]")
                raise typer.Exit()

        restored_count = secrets_store.restore_secrets(
            backup_file, overwrite, passphrase=resolved_passphrase
        )
        
        success_msg = f"[bold green]Restored {restored_count} secrets successfully[/bold green]"
        if conflicts:
            skipped_count = len(conflicts)
            success_msg += f"\n[yellow]Skipped {skipped_count} existing secrets[/yellow]"
        
        console.print(Panel(
            success_msg,
            title="[OK] Restore Complete",
            border_style="green"
        ))

    except Exception as e:
        console.print(Panel(
            f"[bold red]Restore failed[/bold red]\n"
            f"[red]{e}[/red]",
            title="[X] Restore Error",
            border_style="red"
        ))
        raise typer.Exit(1) from e


@app.command("history")
def show_backup_history(
    directory: Annotated[
        str,
        typer.Option(
            "--directory",
            "-d",
            help="Directory to scan for backups (default: current directory)",
        ),
    ] = "",
):
    """Show available backup files and their information.

    Scans the specified directory (or current directory) for backup files
    and displays them in a table with creation date, secret count, and file size.
    Only shows valid backup files with .enc extension.
    """
    from rich.table import Table

    if not directory:
        directory = Path.cwd().as_posix()

    directory_path = Path(directory)
    if not directory_path.exists():
        typer.secho(f"❌ Directory not found: {directory_path}", fg=typer.colors.RED)
        raise typer.Exit(1)

    backup_files = []
    for file_path in directory_path.glob("*.enc"):
        try:
            info = secrets_store.get_backup_info(file_path)
            backup_files.append({
                'path': file_path,
                'created': info['created'],
                'count': info['count'],
                'size': info['size']
            })
        except (KeyError, ValueError, TypeError):
            continue

    if not backup_files:
        console.print(Panel(
            f"[yellow]No backup files found[/yellow]\n"
            f"[bold]Directory:[/bold] [cyan]{directory_path}[/cyan]\n\n"
            "[dim]Backup files should have .enc extension\n"
            "Use 'ofx secret backup' to create backups[/dim]",
            title="[#] Backup History",
            border_style="yellow"
        ))
        return

    backup_files.sort(key=lambda x: x['created'], reverse=True)

    table = Table(
        title=f"[#] Backup History ({len(backup_files)} found)",
        border_style="cyan",
        header_style="bold cyan"
    )
    table.add_column("Filename", style="cyan bold", no_wrap=True)
    table.add_column("Created", style="green")
    table.add_column("Secrets", style="magenta", justify="right")
    table.add_column("Size", style="yellow", justify="right")

    for backup in backup_files:
        filename = backup['path'].name
        created = backup['created'].strftime("%Y-%m-%d %H:%M:%S")
        count = str(backup['count'])
        size = _format_file_size(backup['size'])
        table.add_row(filename, created, count, size)

    console.print(table)


@app.command("migrate")
def migrate_from_files(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation"),
    ] = False,
):
    """Migrate secrets from legacy file-based storage to encrypted store.

    Migrates secrets from individual files in the secrets directory to the
    new encrypted storage format. Legacy files are preserved after migration.
    """
    if not SECRETS_DIR.exists() or not list(SECRETS_DIR.glob("*")):
        console.print(Panel(
            "[yellow]No legacy secrets found to migrate[/yellow]\n"
            f"[dim]Searched in: {SECRETS_DIR}[/dim]",
            title="[~] Migration",
            border_style="yellow"
        ))
        return

    legacy_count = len(list(SECRETS_DIR.glob("*")))

    if not force:
        console.print(Panel(
            f"[bold]Found:[/bold] {legacy_count} legacy secrets\n"
            f"[bold]Location:[/bold] [cyan]{SECRETS_DIR}[/cyan]\n\n"
            "[dim]This will copy secrets to encrypted storage[/dim]",
            title="[~] Migrate Secrets",
            border_style="cyan"
        ))
        confirm = typer.confirm("Migrate to encrypted store?")
        if not confirm:
            console.print("[yellow]Migration cancelled[/yellow]")
            raise typer.Exit()

    migrated = secrets_store.migrate_from_directory(SECRETS_DIR)

    console.print(Panel(
        f"[bold green]Migrated {migrated} secrets successfully[/bold green]\n\n"
        f"[bold]Note:[/bold] Legacy files remain in {SECRETS_DIR}\n"
        "[dim]Delete them manually if no longer needed[/dim]",
        title="[OK] Migration Complete",
        border_style="green"
    ))
