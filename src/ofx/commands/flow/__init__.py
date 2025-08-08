import typer
from async_typer import AsyncTyper
from ofx.commands.flow.run import FlowRunHandler
from ofx.utils.command import command_handler
from ofx.settings import settings

from typing import Optional, List

app = AsyncTyper()

NAME = "flow"

HELP = "Manage and run workflows in the OFX system"


@app.async_command()
async def run(
    workflow_name: str,
    input: Optional[List[str]] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input parameters for the workflow, in the format key=value",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for the workflow results",
    ),
):
    await command_handler(FlowRunHandler, workflow_name, input, output)
