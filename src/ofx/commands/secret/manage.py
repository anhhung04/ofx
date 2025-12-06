import getpass
import json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ofx.settings import SECRETS_DIR, settings
from ofx.utils.secrets import SecretManager

app = typer.Typer()
logger = logging.getLogger(settings.app_branding)
console = Console()


@app.command("set")
def set_secret(
    name: str = typer.Argument(..., help="Secret name"),
    value: Optional[str] = typer.Option(
        None, "--value", "-v", help="Secret value (if not provided, will prompt)"
    ),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Read secret value from file"
    ),
):
    if file:
        if not file.exists():
            typer.secho(f"❌ File not found: {file}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        secret_value = file.read_text().strip()
    elif value:
        secret_value = value
    else:
        secret_value = getpass.getpass(f"Enter value for secret '{name}': ")

    try:
        secret_value = json.loads(secret_value)
    except json.JSONDecodeError:
        pass

    SecretManager.set(name, secret_value)
    typer.secho(f"✅ Secret '{name}' saved to encrypted store", fg=typer.colors.GREEN)


@app.command("get")
def get_secret(
    name: str = typer.Argument(..., help="Secret name"),
    show: bool = typer.Option(False, "--show", "-s", help="Show the secret value"),
):
    value = SecretManager.get(name)

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
def list_secrets():
    secrets = SecretManager.list()

    if not secrets:
        typer.secho("No secrets found", fg=typer.colors.YELLOW)
        return

    table = Table(title="Stored Secrets")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")

    for name in sorted(secrets.keys()):
        value = secrets[name]
        value_type = "JSON" if isinstance(value, (dict, list)) else "String"
        table.add_row(name, value_type)

    console.print(table)


@app.command("delete")
def delete_secret(
    name: str = typer.Argument(..., help="Secret name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    if not SecretManager.exists(name):
        typer.secho(f"❌ Secret '{name}' not found", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"Delete secret '{name}'?")
        if not confirm:
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    SecretManager.delete(name)
    typer.secho(f"✅ Secret '{name}' deleted", fg=typer.colors.GREEN)


@app.command("export")
def export_secrets(
    output: Path = typer.Option(
        Path("secrets.json"), "--output", "-o", help="Output file path"
    ),
):
    count = SecretManager.export(output)

    if not count:
        typer.secho("No secrets to export", fg=typer.colors.YELLOW)
        raise typer.Exit()

    typer.secho(f"✅ Exported {count} secrets to {output}", fg=typer.colors.GREEN)
    typer.secho(
        "⚠️  WARNING: Exported file contains unencrypted secrets!",
        fg=typer.colors.YELLOW,
        bold=True,
    )


@app.command("import")
def import_secrets(
    file: Path = typer.Argument(..., help="JSON file containing secrets"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Overwrite existing secrets"
    ),
):
    try:
        imported = SecretManager.import_from_file(file, overwrite)
    except FileNotFoundError as e:
        typer.secho(f"❌ {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.secho(f"❌ {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(f"✅ Imported {imported} secrets", fg=typer.colors.GREEN)


@app.command("clear")
def clear_secrets(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    secrets = SecretManager.list()

    if not secrets:
        typer.secho("No secrets to clear", fg=typer.colors.YELLOW)
        return

    if not force:
        confirm = typer.confirm(f"Delete ALL {len(secrets)} secrets?")
        if not confirm:
            typer.secho("Cancelled", fg=typer.colors.YELLOW)
            raise typer.Exit()

    SecretManager.clear()
    typer.secho("✅ All secrets cleared", fg=typer.colors.GREEN)


@app.command("store")
def show_store_location():
    info = SecretManager.get_store_info()

    typer.secho(f"Secret store: {info['path']}", fg=typer.colors.CYAN)
    typer.secho(
        "Set OFX_SECRETS_STORE environment variable to change location",
        fg=typer.colors.YELLOW,
        dim=True,
    )

    if info["exists"]:
        typer.secho(f"Store size: {info['size']} bytes", fg=typer.colors.CYAN)
        typer.secho(f"Secret count: {info['count']}", fg=typer.colors.CYAN)


@app.command("migrate")
def migrate_from_files(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
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

    migrated = SecretManager.migrate_from_directory(SECRETS_DIR)

    typer.secho(
        f"✅ Migrated {migrated} secrets to encrypted store", fg=typer.colors.GREEN
    )
    typer.secho(
        f"Legacy files remain in {SECRETS_DIR} (delete manually if desired)",
        fg=typer.colors.YELLOW,
        dim=True,
    )
