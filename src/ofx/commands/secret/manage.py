import json
import logging
from pathlib import Path
from typing import Annotated, Any

import typer

from ofx.commands.ui_helpers import (
    print_error,
    print_info,
    print_success,
    print_warning,
)
from ofx.settings import SECRETS_DIR, get_console, settings
from ofx.utils import secrets as secrets_store

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
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

    return typer.prompt(f"Enter value for secret '{name}'", hide_input=True)


def _resolve_passphrase(passphrase: str, ask: bool) -> str | None:
    """Return the passphrase from flag or prompt; prompt wins when requested."""
    if ask:
        return (
            typer.prompt(
                "Enter passphrase for secrets store (leave blank for none)",
                hide_input=True,
            ).strip()
            or None
        )
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
        typer.secho(
            "No secrets to backup; skipping backup creation", fg=typer.colors.YELLOW
        )
        return

    typer.secho(
        f"💾 Backup created at {backup_path_obj} ({count} secrets)",
        fg=typer.colors.CYAN,
    )


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
    from rich.table import Table

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

    table = Table(
        title=f"[*] Stored Secrets ({len(filtered_secrets)} found)",
        border_style="cyan",
        header_style="bold cyan",
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

    from rich.table import Table

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

    table = Table(
        title=f"🔍 Search Results for '{pattern}' ({len(matches)} found)",
        border_style="cyan",
        header_style="bold cyan",
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
        if len(value) > 50 and any(char in value for char in [".", "/", "=", "+"]):
            return "token"
        elif len(value) > 20 and any(char in value for char in ["@", "."]):
            return "api-key"
        elif (
            len(value) >= 8
            and any(char.isdigit() for char in value)
            and any(char.isupper() for char in value)
        ):
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
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _format_secret_value(value) -> str:
    """Format a secret value for display in tables"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=0, separators=(",", ":"))
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
        print_warning("Backup", "No secrets to backup")
        return

    if not output_file:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"ofx_secrets_backup_{timestamp}.enc"

    output_path = Path(output_file)
    if output_path.exists() and not force:
        print_error(
            "File Exists",
            f"Backup file already exists: {output_path}",
            "Use --force to overwrite",
        )
        raise typer.Exit(1)

    try:
        count = secrets_store.backup_secrets(
            output_path, passphrase=resolved_passphrase
        )

        file_size = output_path.stat().st_size
        print_success(
            "Backup Complete",
            "Backup created successfully",
            details={
                "File": str(output_path),
                "Secrets": count,
                "Size": _format_file_size(file_size),
            },
        )

    except Exception as e:
        print_error(
            "Backup Error",
            "Backup failed",
            details=str(e),
        )
        raise typer.Exit(1) from e


@app.command("restore")
def restore_secrets(
    backup_file: Annotated[
        Path, typer.Argument(..., help="Backup file to restore from")
    ],
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
    console = get_console()
    if not backup_file.exists():
        print_error(
            "File Not Found",
            "Backup file not found",
            details=str(backup_file),
        )
        raise typer.Exit(1)

    _maybe_backup_store(backup_to, resolved_passphrase, backup_overwrite)

    try:
        info = secrets_store.get_backup_info(
            backup_file, passphrase=resolved_passphrase
        )

        print_success(
            "Backup Information",
            "Backup metadata loaded",
            details={
                "File": str(backup_file),
                "Created": info["created"],
                "Secrets": info["count"],
                "Size": _format_file_size(info["size"]),
            },
        )

        if dry_run:
            print_warning(
                "Preview",
                "Dry run mode - no changes will be made",
            )
            table = Table(
                title="Secrets to be Restored",
                border_style="cyan",
                header_style="bold cyan",
            )
            table.add_column("Name", style="cyan bold")
            table.add_column("Type", style="magenta")
            table.add_column("Status", style="yellow")

            current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
            for name, value in info["secrets"].items():
                status = (
                    "New"
                    if name not in current_secrets
                    else ("Overwrite" if overwrite else "Skip")
                )
                secret_type = _get_secret_type(value)
                table.add_row(name, secret_type, status)

            console.print(table)
            return

        current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
        conflicts = []
        for name in info["secrets"].keys():
            if name in current_secrets and not overwrite:
                conflicts.append(name)

        if conflicts:
            conflict_list = "\n".join([f"• {name}" for name in conflicts[:5]])
            if len(conflicts) > 5:
                conflict_list += f"\n• ... and {len(conflicts) - 5} more"

            print_warning(
                "Conflicts Detected",
                f"{len(conflicts)} secrets already exist and will be skipped:",
                hint=(
                    f"{conflict_list}\n\nUse --overwrite to replace existing secrets"
                ),
            )

            if not typer.confirm("Continue with restore?"):
                console.print("[yellow]Operation cancelled[/yellow]")
                raise typer.Exit()

        restored_count = secrets_store.restore_secrets(
            backup_file, overwrite, passphrase=resolved_passphrase
        )

        success_msg = (
            f"[bold green]Restored {restored_count} secrets successfully[/bold green]"
        )
        if conflicts:
            skipped_count = len(conflicts)
            success_msg += (
                f"\n[yellow]Skipped {skipped_count} existing secrets[/yellow]"
            )

        print_success(
            "Restore Complete",
            success_msg,
        )

    except Exception as e:
        print_error(
            "Restore Error",
            "Restore failed",
            details=str(e),
        )
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

    console = get_console()
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
            backup_files.append(
                {
                    "path": file_path,
                    "created": info["created"],
                    "count": info["count"],
                    "size": info["size"],
                }
            )
        except (KeyError, ValueError, TypeError):
            continue

    if not backup_files:
        print_warning(
            "Backup History",
            "No backup files found",
            hint=(
                f"Directory: {directory_path}\n"
                "Backup files should have .enc extension.\n"
                "Use 'ofx secret backup' to create backups."
            ),
        )
        return

    backup_files.sort(key=lambda x: x["created"], reverse=True)

    table = Table(
        title=f"[#] Backup History ({len(backup_files)} found)",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("Filename", style="cyan bold", no_wrap=True)
    table.add_column("Created", style="green")
    table.add_column("Secrets", style="magenta", justify="right")
    table.add_column("Size", style="yellow", justify="right")

    for backup in backup_files:
        filename = backup["path"].name
        created = backup["created"].strftime("%Y-%m-%d %H:%M:%S")
        count = str(backup["count"])
        size = _format_file_size(backup["size"])
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
        print_warning(
            "Migration",
            "No legacy secrets found to migrate",
            hint=f"Searched in: {SECRETS_DIR}",
        )
        return

    legacy_count = len(list(SECRETS_DIR.glob("*")))

    if not force:
        print_warning(
            "Migrate Secrets",
            f"Found {legacy_count} legacy secrets",
            hint=(
                f"Location: {SECRETS_DIR}\nThis will copy secrets to encrypted storage."
            ),
        )
        confirm = typer.confirm("Migrate to encrypted store?")
        if not confirm:
            get_console().print("[yellow]Migration cancelled[/yellow]")
            raise typer.Exit()

    migrated = secrets_store.migrate_from_directory(SECRETS_DIR)

    print_success(
        "Migration Complete",
        f"Migrated {migrated} secrets successfully",
        details={
            "Note": (
                f"Legacy files remain in {SECRETS_DIR}. "
                "Delete them manually if no longer needed."
            )
        },
    )
