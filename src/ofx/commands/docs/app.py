import typer
from typing import Annotated

app = typer.Typer(
    help="Display OFX API documentation"
)

NAME = "docs"

HELP = "Display OFX API documentation"

from ofx.commands.docs.api import show_api

app.callback(invoke_without_command=True)(show_api)
