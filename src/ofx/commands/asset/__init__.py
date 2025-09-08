import typer
from ofx.commands.asset.init import InitHandler


app = typer.Typer()

NAME = "asset"

HELP = "Manage OFX assets."


@app.command()
def init():
    """
    Init new OFX asserts
    """
    InitHandler().run()  # type: ignore
