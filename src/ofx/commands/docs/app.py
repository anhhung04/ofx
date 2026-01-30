import typer

from ofx.commands.docs.api import show_api

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

NAME = "docs"

HELP = "Display OFX API documentation"

app.callback(invoke_without_command=True)(show_api)
