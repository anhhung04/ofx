import typer

from ofx.settings import settings, BANNER
from ofx.utils.log import reload_logging_config
from ofx.commands import flow, dump, asset

app = typer.Typer(pretty_exceptions_show_locals=False)


@app.callback()
def main_callback(
    grepable: bool = typer.Option(
        False,
        "--grepable",
        "-g",
        help="Output in grep-friendly (plain) format, disables rich formatting and color logs.",
    )
):
    global settings
    settings.grepable = grepable
    reload_logging_config(settings)
    if not settings.grepable:
        typer.echo(BANNER, err=True, color=True)


def add_app(sub_app):
    app.add_typer(sub_app.app, name=sub_app.NAME, help=sub_app.HELP)


add_app(flow)
add_app(dump)
add_app(asset)


def main():
    """
    Main entry point for the OFX CLI application.
    """
    try:
        app()
    except Exception as e:
        typer.secho(f"🚨 Error: {e}", fg=typer.colors.RED, bold=True)
        return typer.Exit(code=1)
