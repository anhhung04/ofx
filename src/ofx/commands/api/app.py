"""API documentation command for OFX."""

import typer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "api"
HELP = "Display OFX API reference"


@app.command("show")
def show(
    module: str = typer.Option(
        "", "--module", "-m", help="Optional API module name to document"
    ),
    function: str = typer.Option(
        "", "--function", "-f", help="Specific function to display details for"
    ),
    list_modules: bool = typer.Option(
        False, "--list", "-l", help="List all available API modules"
    ),
):
    """Proxy to the original show_api implementation."""
    from ofx.commands.api.api import show_api

    show_api(module=module, function=function, list_modules=list_modules)
