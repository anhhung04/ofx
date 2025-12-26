import typer

from ofx.commands import asset, docs, doctor, dump, flow, project, secret
from ofx.settings import BANNER

app = typer.Typer(pretty_exceptions_show_locals=False)


def add_app(sub_app):
    help = sub_app.HELP
    if hasattr(sub_app, "ALIAS"):
        help = help + f" (alias {', '.join(sub_app.ALIAS)})"
        for alias in sub_app.ALIAS:
            app.add_typer(
                sub_app.app,
                name=alias,
                help=help,
                hidden=True,
            )
    app.add_typer(
        sub_app.app,
        name=sub_app.NAME,
        help=help,
    )


add_app(flow)
add_app(dump)
add_app(asset)
add_app(project)
add_app(docs)
add_app(doctor)
add_app(secret)


def main():
    """Main entry point for the OFX CLI application"""
    try:
        typer.echo(BANNER)
        app()
    except Exception as e:
        typer.secho(f"🚨 Error: {e}", fg=typer.colors.RED, bold=True)
        return typer.Exit(code=1)
