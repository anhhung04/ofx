import json
from pathlib import Path

import typer

from ofx.utils import secrets as secrets_store

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
