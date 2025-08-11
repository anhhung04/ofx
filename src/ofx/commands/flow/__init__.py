import typer
from typing import Optional, List
from async_typer import AsyncTyper

from ofx.commands.flow.run import FlowRunHandler

app = AsyncTyper()

NAME = "flow"

HELP = "Manage and run workflows in the OFX system"


@app.async_command()
async def run(
    workflow_name=typer.Argument(..., help="Name of the workflow to run"),
    input=typer.Option(
        None,
        "-i",
        "--input",
        help="Input parameters for the workflow in key=value format. Can be specified multiple times.",
    ),
    output=typer.Option(
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
