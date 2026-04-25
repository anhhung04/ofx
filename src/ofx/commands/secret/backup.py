import logging
from pathlib import Path
from typing import Annotated

import typer

from ofx.commands.secret.helpers import (
    _format_file_size,
    _get_secret_type,
    _maybe_backup_store,
    _resolve_passphrase,
)
from ofx.commands.ui_helpers import (
    error_exit,
    print_success,
    print_warning,
)
from ofx.settings import SECRETS_DIR, get_console, settings
from ofx.utils import secrets as secrets_store

backup_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
logger = logging.getLogger(settings.app_branding)


@backup_app.command("create")
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
        error_exit(
            "File Exists",
            f"Backup file already exists: {output_path}",
            "Use --force to overwrite",
        )

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
        error_exit(
            "Backup Error",
            "Backup failed",
            details=str(e),
        )


@backup_app.command("restore")
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
        error_exit(
            "File Not Found",
            "Backup file not found",
            details=str(backup_file),
        )

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
        error_exit(
            "Restore Error",
            "Restore failed",
            details=str(e),
        )


@backup_app.command("history")
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
                "Use 'ofx secret backup create' to create backups."
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


@backup_app.command("migrate")
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
