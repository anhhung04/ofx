import getpass
import json
import logging
from pathlib import Path
from typing import Any, Dict

import typer

from ofx.settings import SECRETS_DIR, settings
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


def _resolve_passphrase(passphrase: str | None, ask: bool) -> str | None:
    """Return the passphrase from flag or prompt; prompt wins when requested."""
    if ask:
        return getpass.getpass("Enter passphrase: ")
    return passphrase


def _maybe_backup_store(
    backup_path: Path | None, passphrase: str | None, overwrite: bool
) -> None:
    """Create a backup if requested, failing fast on overwrite collisions."""
    if backup_path is None:
        return

    if backup_path.exists() and not overwrite:
        typer.secho(
            f"❌ Backup file already exists: {backup_path}. Use --backup-overwrite to replace",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    count = secrets_store.backup_secrets(backup_path, passphrase=passphrase)

    if count == 0:
        typer.secho("No secrets to backup; skipping backup creation", fg=typer.colors.YELLOW)
        return

    typer.secho(
        f"💾 Backup created at {backup_path} ({count} secrets)",
        fg=typer.colors.CYAN,
    )


@app.command("set")
def set_secret(
    name: str = typer.Argument(..., help="Secret name"),
    value: str | None = typer.Option(
        None, "--value", "-v", help="Secret value (if not provided, will prompt)"
    ),
    file: Path | None = typer.Option(
        None, "--file", "-f", help="Read secret value from file"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing secret without prompt"
    ),
):
    """Store a secret value in encrypted storage.

    The secret can be provided directly via --value, read from a file via --file,
    or entered interactively if neither option is provided. JSON values are
    automatically detected and stored as structured data.
    """
    secret_value = _resolve_secret_input(name, value, file)
    if secrets_store.secret_exists(name) and not force:
        if not typer.confirm(f"Secret '{name}' exists. Overwrite?"):
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    try:
        secret_value = json.loads(secret_value)
    except json.JSONDecodeError:
        # Keep raw string when JSON decoding is not applicable
        pass

    secrets_store.set_secret(name, secret_value)
    typer.secho(f"✅ Secret '{name}' saved to encrypted store", fg=typer.colors.GREEN)


@app.command("get")
def get_secret(
    name: str = typer.Argument(..., help="Secret name"),
    show: bool = typer.Option(False, "--show", "-s", help="Show the secret value"),
):
    """Retrieve a secret value from encrypted storage.

    By default, only confirms the secret exists without displaying its value.
    Use --show to display the actual secret value. JSON secrets are displayed
    in formatted output.
    """
    value = secrets_store.get_secret(name)

    if value is None:
        typer.secho(f"❌ Secret '{name}' not found", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if show:
        if isinstance(value, (dict, list)):
            typer.echo(json.dumps(value, indent=2))
        else:
            typer.echo(value)
    else:
        typer.secho(f"Secret '{name}' exists in encrypted store", fg=typer.colors.CYAN)
        typer.secho("Use --show to display the value", fg=typer.colors.YELLOW, dim=True)


@app.command("list")
def list_secrets(
    filter_type: str | None = typer.Option(
        None, "--filter", "-f", help="Filter by type (string, json, api-key, password, token)"
    ),
    search: str | None = typer.Option(
        None, "--search", "-s", help="Search in secret names"
    ),
    show_values: bool = typer.Option(
        False, "--show-values", help="Show secret values (WARNING: displays sensitive data)"
    ),
):
    """List all stored secrets with optional filtering and searching.

    Displays secrets in a table format with name and type information.
    Supports filtering by secret type and searching within secret names.
    Use --show-values with caution as it displays sensitive data.
    """
    from rich.table import Table

    from ofx.settings import get_console
    console = get_console()
    secrets = secrets_store.list_secrets()

    if not secrets:
        typer.secho("No secrets found", fg=typer.colors.YELLOW)
        return

    # Apply filters
    filtered_secrets: Dict[str, Any] = {}
    for name, value in secrets.items():
        # Search filter
        if search and search.lower() not in name.lower():
            continue

        # Type filter
        if filter_type:
            secret_type = _get_secret_type(value)
            if secret_type != filter_type.lower():
                continue

        filtered_secrets[name] = value

    if not filtered_secrets:
        typer.secho("No secrets match the specified filters", fg=typer.colors.YELLOW)
        return

    table = Table(title=f"Stored Secrets ({len(filtered_secrets)} found)")
    table.add_column("Name", style="cyan", no_wrap=True)
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
    pattern: str = typer.Argument(..., help="Search pattern (supports wildcards: * and ?)"),
    show_values: bool = typer.Option(
        False, "--show-values", help="Show secret values (WARNING: displays sensitive data)"
    ),
):
    """Search for secrets by name pattern with wildcard support.

    Supports Unix shell-style wildcards: * matches any sequence of characters,
    ? matches any single character. Search is case-insensitive.
    Use --show-values with caution as it displays sensitive data.
    """
    import fnmatch

    from rich.table import Table

    from ofx.settings import get_console
    console = get_console()
    secrets = secrets_store.list_secrets()

    if not secrets:
        typer.secho("No secrets found", fg=typer.colors.YELLOW)
        return

    matches: Dict[str, Any] = {}

    for name, value in secrets.items():
        if fnmatch.fnmatch(name.lower(), pattern.lower()):
            matches[name] = value

    if not matches:
        typer.secho(f"No secrets match pattern: {pattern}", fg=typer.colors.YELLOW)
        return

    table = Table(title=f"Search Results for '{pattern}' ({len(matches)} found)")
    table.add_column("Name", style="cyan", no_wrap=True)
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
        # Try to detect common secret types
        if len(value) > 50 and any(char in value for char in ['.', '/', '=', '+']):
            return "token"  # Likely API token or key
        elif len(value) > 20 and any(char in value for char in ['@', '.']):
            return "api-key"  # Likely API key or token
        elif len(value) >= 8 and any(char.isdigit() for char in value) and any(char.isupper() for char in value):
            return "password"  # Likely password
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
        # Truncate long strings
        if len(value) > 50:
            return value[:47] + "..."
        return value
    else:
        return str(value)


@app.command("delete")
def delete_secret(
    name: str = typer.Argument(..., help="Secret name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup before deletion (path to .enc file)",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite backup file if it exists"
    ),
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
    typer.secho(f"✅ Secret '{name}' deleted", fg=typer.colors.GREEN)


@app.command("export")
def export_secrets(
    output: Path = typer.Option(
        Path("secrets.json"), "--output", "-o", help="Output file path"
    ),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup before export (path to .enc file)",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite backup file if it exists"
    ),
):
    """Export secrets to a file for backup or migration.

    Creates an unencrypted JSON file containing all secrets. Keep the exported
    file secure as it contains sensitive data. Use the backup command for
    encrypted backups instead.
    """
    _maybe_backup_store(backup_to, None, backup_overwrite)
    count = secrets_store.export_secrets(output)

    if not count:
        typer.secho("No secrets to export", fg=typer.colors.YELLOW)
        raise typer.Exit()

    typer.secho(f"✅ Exported {count} secrets to {output}", fg=typer.colors.GREEN)
    typer.secho(
        "⚠️ WARNING: Exported file contains unencrypted secrets!",
        fg=typer.colors.YELLOW,
        bold=True,
    )


@app.command("import")
def import_secrets(
    file: Path = typer.Argument(..., help="JSON file containing secrets"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing secrets"
    ),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup before import (path to .enc file)",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite backup file if it exists"
    ),
):
    """Import secrets from a JSON file.

    Reads secrets from an unencrypted JSON file and stores them in encrypted
    storage. By default, skips existing secrets unless --overwrite is used.
    """
    try:
        _maybe_backup_store(backup_to, None, backup_overwrite)
        imported = secrets_store.import_secrets_from_file(file, overwrite)
    except FileNotFoundError as e:
        typer.secho(f"❌ {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except ValueError as e:
        typer.secho(f"❌ {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    typer.secho(f"✅ Imported {imported} secrets", fg=typer.colors.GREEN)


@app.command("clear")
def clear_secrets(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup before clearing (path to .enc file)",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite backup file if it exists"
    ),
):
    """Clear all secrets from encrypted storage.

    Permanently removes ALL secrets from the store. Requires confirmation
    unless --force is used. This action cannot be undone.
    """
    secrets = secrets_store.list_secrets()

    if not secrets:
        typer.secho("No secrets to clear", fg=typer.colors.YELLOW)
        return

    _maybe_backup_store(backup_to, None, backup_overwrite)

    if not force:
        confirm = typer.confirm(f"Delete ALL {len(secrets)} secrets?")
        if not confirm:
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    secrets_store.clear_secrets()
    typer.secho("✅ All secrets cleared", fg=typer.colors.GREEN)


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
    output_file: Path | None = typer.Option(
        None, "--output", "-o", help="Output file path (default: auto-generated)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing backup file"
    ),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup of current store before writing new backup",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite pre-backup file if it exists"
    ),
    passphrase: str | None = typer.Option(
        None,
        "--passphrase",
        "-p",
        envvar="OFX_SECRETS_PASSPHRASE",
        help="Passphrase to unlock the secret store (env: OFX_SECRETS_PASSPHRASE)",
    ),
    ask_passphrase: bool = typer.Option(
        False, "--ask-passphrase", help="Prompt for passphrase interactively"
    ),
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
        typer.secho("No secrets to backup", fg=typer.colors.YELLOW)
        return

    # Generate default filename with timestamp if not provided
    if output_file is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(f"ofx_secrets_backup_{timestamp}.enc")

    # Check if file exists
    if output_file.exists() and not force:
        typer.secho(f"❌ Backup file already exists: {output_file}", fg=typer.colors.RED)
        typer.secho("Use --force to overwrite", fg=typer.colors.YELLOW)
        raise typer.Exit(1)

    try:
        # Create encrypted backup
        count = secrets_store.backup_secrets(output_file, passphrase=resolved_passphrase)
        typer.secho(f"✅ Created encrypted backup: {output_file}", fg=typer.colors.GREEN)
        typer.secho(f"[INFO] Backed up {count} secrets", fg=typer.colors.CYAN)

        # Show file info
        file_size = output_file.stat().st_size
        typer.secho(f"[SIZE] File size: {_format_file_size(file_size)}", fg=typer.colors.CYAN)

    except Exception as e:
        typer.secho(f"❌ Backup failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command("restore")
def restore_secrets(
    backup_file: Path = typer.Argument(..., help="Backup file to restore from"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing secrets with same names"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be restored without actually doing it"
    ),
    backup_to: Path | None = typer.Option(
        None,
        "--backup-to",
        help="Create an encrypted backup of current store before restoring",
    ),
    backup_overwrite: bool = typer.Option(
        False, "--backup-overwrite", help="Overwrite pre-backup file if it exists"
    ),
    passphrase: str | None = typer.Option(
        None,
        "--passphrase",
        "-p",
        envvar="OFX_SECRETS_PASSPHRASE",
        help="Passphrase to unlock the secret store (env: OFX_SECRETS_PASSPHRASE)",
    ),
    ask_passphrase: bool = typer.Option(
        False, "--ask-passphrase", help="Prompt for passphrase interactively"
    ),
):
    """Restore secrets from an encrypted backup file.

    Restores secrets from a backup created with the backup command.
    Supports conflict resolution when secrets already exist.
    Use --dry-run to preview what would be restored without making changes.
    """
    from rich.table import Table

    from ofx.settings import get_console
    console = get_console()
    resolved_passphrase = _resolve_passphrase(passphrase, ask_passphrase)
    if not backup_file.exists():
        typer.secho(f"❌ Backup file not found: {backup_file}", fg=typer.colors.RED)
        raise typer.Exit(1)

    _maybe_backup_store(backup_to, resolved_passphrase, backup_overwrite)

    try:
        # Get backup info without restoring
        info = secrets_store.get_backup_info(backup_file, passphrase=resolved_passphrase)

        typer.secho(f"[INFO] Backup file: {backup_file}", fg=typer.colors.CYAN)
        typer.secho(f"[DATE] Created: {info['created']}", fg=typer.colors.CYAN)
        typer.secho(f"[COUNT] Secrets: {info['count']}", fg=typer.colors.CYAN)
        typer.secho(f"[SIZE] Size: {_format_file_size(info['size'])}", fg=typer.colors.CYAN)

        if dry_run:
            typer.secho("\n[DRY RUN] Dry run - showing secrets that would be restored:", fg=typer.colors.YELLOW)
            table = Table()
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Status", style="yellow")

            current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
            for name, value in info['secrets'].items():
                status = "New" if name not in current_secrets else ("Overwrite" if overwrite else "Skip")
                secret_type = _get_secret_type(value)
                table.add_row(name, secret_type, status)

            console.print(table)
            return

        # Check for conflicts
        current_secrets = secrets_store.list_secrets(passphrase=resolved_passphrase)
        conflicts = []
        for name in info['secrets'].keys():
            if name in current_secrets and not overwrite:
                conflicts.append(name)

        if conflicts:
            typer.secho(f"\n⚠️ {len(conflicts)} secrets already exist and would be skipped:", fg=typer.colors.YELLOW)
            for name in conflicts[:5]:  # Show first 5
                typer.secho(f"   • {name}", fg=typer.colors.YELLOW)
            if len(conflicts) > 5:
                typer.secho(f"   ... and {len(conflicts) - 5} more", fg=typer.colors.YELLOW)

            if not typer.confirm("Continue with restore?"):
                typer.secho("Cancelled", fg=typer.colors.YELLOW)
                raise typer.Exit()

        # Perform restore
        restored_count = secrets_store.restore_secrets(
            backup_file, overwrite, passphrase=resolved_passphrase
        )
        typer.secho(f"✅ Restored {restored_count} secrets from backup", fg=typer.colors.GREEN)

        if conflicts:
            skipped_count = len(conflicts)
            typer.secho(f"[SKIP] Skipped {skipped_count} existing secrets", fg=typer.colors.YELLOW)

    except Exception as e:
        typer.secho(f"❌ Restore failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e


@app.command("history")
def show_backup_history(
    directory: Path | None = typer.Option(
        None, "--directory", "-d", help="Directory to scan for backups (default: current directory)"
    ),
):
    """Show available backup files and their information.

    Scans the specified directory (or current directory) for backup files
    and displays them in a table with creation date, secret count, and file size.
    Only shows valid backup files with .enc extension.
    """
    from rich.table import Table

    from ofx.settings import get_console
    console = get_console()
    if directory is None:
        directory = Path.cwd()

    if not directory.exists():
        typer.secho(f"❌ Directory not found: {directory}", fg=typer.colors.RED)
        raise typer.Exit(1)

    # Find backup files (files ending with .enc that contain backup data)
    backup_files = []
    for file_path in directory.glob("*.enc"):
        try:
            info = secrets_store.get_backup_info(file_path)
            backup_files.append({
                'path': file_path,
                'created': info['created'],
                'count': info['count'],
                'size': info['size']
            })
        except (KeyError, ValueError, TypeError):
            # Skip files that aren't valid backups
            continue

    if not backup_files:
        typer.secho(f"No backup files found in {directory}", fg=typer.colors.YELLOW)
        typer.secho("Backup files should have .enc extension", fg=typer.colors.YELLOW)
        return

    # Sort by creation date (newest first)
    backup_files.sort(key=lambda x: x['created'], reverse=True)

    table = Table(title=f"Backup History ({len(backup_files)} found)")
    table.add_column("Filename", style="cyan", no_wrap=True)
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
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Migrate secrets from legacy file-based storage to encrypted store.

    Migrates secrets from individual files in the secrets directory to the
    new encrypted storage format. Legacy files are preserved after migration.
    """
    if not SECRETS_DIR.exists() or not list(SECRETS_DIR.glob("*")):
        typer.secho("No legacy secrets found to migrate", fg=typer.colors.YELLOW)
        return

    legacy_count = len(list(SECRETS_DIR.glob("*")))

    if not force:
        typer.secho(
            f"Found {legacy_count} secrets in {SECRETS_DIR}", fg=typer.colors.CYAN
        )
        confirm = typer.confirm("Migrate to encrypted store?")
        if not confirm:
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    migrated = secrets_store.migrate_from_directory(SECRETS_DIR)

    typer.secho(
        f"✅ Migrated {migrated} secrets to encrypted store", fg=typer.colors.GREEN
    )
    typer.secho(
        f"Legacy files remain in {SECRETS_DIR} (delete manually if desired)",
        fg=typer.colors.YELLOW,
        dim=True,
    )
