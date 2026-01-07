import typer
from typing import Annotated
from async_typer import AsyncTyper

app = AsyncTyper()

NAME = "flow"

ALIAS = ["x", "task"]

HELP = "Manage and run workflows in the OFX system"

@app.async_command()
async def run(
    workflow_name: Annotated[
        str, typer.Argument(help="Name of the workflow to run")
    ],
    input: Annotated[
        list[str],
        typer.Option(
            "-i",
            "--input",
            help="Input parameters for the workflow in key=value format. Can be specified multiple times.",
        ),
    ] = [],
    output: Annotated[
        str,
        typer.Option(
            "-o",
            "--output",
            help="Output path for the workflow results. If not specified, defaults to the current directory.",
        ),
    ] = "",
    profile: Annotated[
        bool,
        typer.Option(
            "--profile",
            help="Enable performance profiling and output timing information.",
        ),
    ] = False,
):
    from ofx.commands.flow.run import FlowRunHandler

    await FlowRunHandler(
        workflow_name=workflow_name,
        input=input,
        output=output,
        profile=profile,
    ).run()


@app.command()
def validate(
    workflow_name: Annotated[
        str, typer.Argument(help="Name of the workflow to validate")
    ] = "",
):
    """Validate a workflow configuration"""
    from ofx.commands.flow.validate import ValidateHandler

    ValidateHandler().run(workflow_name=workflow_name)


@app.command()
def update():
    """Update the workflow configuration"""
    from ofx.commands.flow.update import UpdateHandler

    UpdateHandler().run()


@app.command()
def visualize(
    workflow_name: Annotated[
        str, typer.Argument(..., help="Name of the workflow to visualize")
    ],
    output: Annotated[
        str,
        typer.Option(
            "-o",
            "--output",
            help="Output path for the visualization file. If not specified, displays in terminal.",
        ),
    ] = "",
    format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format for visualization (dot, png, svg, pdf). Default is dot.",
        ),
    ] = "dot",
):
    """Visualize workflow as a directed acyclic graph (DAG)"""
    from ofx.commands.flow.visualize import VisualizeHandler

    VisualizeHandler(
        workflow_name=workflow_name,
        output=output,
        format=format,
    ).run()
