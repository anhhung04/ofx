from ofx.commands.secret.backup import backup_app
from ofx.commands.secret.manage import app

app.add_typer(backup_app, name="backup", help="Backup and restore secrets")

NAME = "secret"
HELP = "Manage secrets for workflows"

__all__ = ["app", "NAME", "HELP"]
