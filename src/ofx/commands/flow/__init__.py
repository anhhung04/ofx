from typing import Annotated, List, Optional

import typer
from async_typer import AsyncTyper

app = AsyncTyper()

NAME = "flow"


ALIAS = ["x", "task"]

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
    from ofx.commands.flow.run import FlowRunHandler

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
    from ofx.commands.flow.validate import ValidateHandler

    ValidateHandler().run(workflow_name=workflow_name)


@app.command()
def update():
    """
    Update the workflow configuration.
    """
    from ofx.commands.flow.update import UpdateHandler

    UpdateHandler().run()
