import typer
from async_typer import AsyncTyper

from ofx.commands.flow.run import FlowRunHandler
from typing import List, Optional

app = AsyncTyper()

NAME = "flow"

HELP = "Manage and run workflows in the OFX system"


@app.async_command()
async def run(
    workflow_name=typer.Argument(..., help="Name of the workflow to run"),
    input: List[str] = typer.Option(
        None,
        "-i",
        "--input",
        help="Input parameters for the workflow in key=value format. Can be specified multiple times.",
    ),
    output: str = typer.Option(
        None,
        "-o",
        "--output",
        help="Output path for the workflow results. If not specified, defaults to the current directory.",
    ),
):
    await FlowRunHandler(
        workflow_name=workflow_name,
        input=input,
        output=output,
    ).run()
