import typer
from async_typer import AsyncTyper

from ofx.commands.flow.run import FlowRunHandler
from ofx.commands.flow.validate import ValidateHandler
from typing import List, Annotated, Optional

app = AsyncTyper()

NAME = "flow"

HELP = "Manage and run workflows in the OFX system"


@app.async_command()
async def run(
    workflow_name: Annotated[
        str, typer.Argument(..., help="Name of the workflow to run")
    ],
    input: Annotated[
        Optional[List[str]],
        typer.Option(
            "-i",
            "--input",
            help="Input parameters for the workflow in key=value format. Can be specified multiple times.",
        ),
    ] = None,
    output: Annotated[
        Optional[str],
        typer.Option(
            "-o",
            "--output",
            help="Output path for the workflow results. If not specified, defaults to the current directory.",
        ),
    ] = None,
):
    await FlowRunHandler(
        workflow_name=workflow_name,
        input=input,
        output=output,
    ).run()


@app.command()
def validate(
    workflow_name: Annotated[
        str, typer.Argument(..., help="Name of the workflow to validate")
    ],
):
    """
    Validate a workflow configuration.
    """
    ValidateHandler().run(workflow_name=workflow_name)
