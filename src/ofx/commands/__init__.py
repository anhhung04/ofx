import typer

from ofx.commands import flow

app = typer.Typer()

app.add_typer(flow.app, name=flow.NAME, help=flow.HELP)
