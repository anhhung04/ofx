import typer

from ofx.settings import settings, BANNER
from ofx.utils.log import reload_logging_config

from ofx.commands import flow, dump

app = typer.Typer()


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


app.add_typer(flow.app, name=flow.NAME, help=flow.HELP)
app.add_typer(dump.app, name=dump.NAME, help=dump.HELP)
