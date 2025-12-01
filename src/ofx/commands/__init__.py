import typer

from ofx.commands import api, asset, dump, flow, project
from ofx.settings import BANNER

app = typer.Typer(pretty_exceptions_show_locals=False)


def add_app(sub_app):
    app.add_typer(sub_app.app, name=sub_app.NAME, help=sub_app.HELP)


add_app(flow)
add_app(dump)
add_app(asset)
add_app(project)
add_app(api)


def main():
    """
    Main entry point for the OFX CLI application.
    """
    try:
        typer.echo(BANNER)
        app()
    except Exception as e:
        typer.secho(f"🚨 Error: {e}", fg=typer.colors.RED, bold=True)
        return typer.Exit(code=1)
