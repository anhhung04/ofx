import asyncio
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "flow"

ALIAS = ["x", "task"]

HELP = "Manage and run workflows in the OFX system"


@app.command()
def run(
    workflow_name: Annotated[str, typer.Argument(help="Name of the workflow to run")],
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
    durable: Annotated[
        bool | None,
        typer.Option(
            "--durable/--no-durable",
            help="Enable or disable durable execution checkpoints.",
        ),
    ] = None,
    resume: Annotated[
        bool | None,
        typer.Option(
            "--resume/--no-resume",
            help="Resume from last completed step when checkpoints exist.",
        ),
    ] = None,
    durable_backend: Annotated[
        str | None,
        typer.Option(
            "--durable-backend",
            help="Durable backend to use: file or redis.",
        ),
    ] = None,
    durable_redis_prefix: Annotated[
        str | None,
        typer.Option(
            "--durable-redis-prefix",
            help="Redis key prefix for durable checkpoints.",
        ),
    ] = None,
):
    from ofx.commands.flow.run import FlowRunHandler

    asyncio.run(
        FlowRunHandler(
            workflow_name=workflow_name,
            input=input,
            output=output,
            profile=profile,
            durable=durable,
            resume=resume,
            durable_backend=durable_backend,
            durable_redis_prefix=durable_redis_prefix,
        ).run()
    )


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
def tools(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to install tools for. Use --all to process all workflows."
        ),
    ] = "",
    all_workflows: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Install tools from all workflows in the configured directories.",
        ),
    ] = False,
):
    """Install workflow tool dependencies"""
    from ofx.commands.flow.tools import ToolsInstallHandler

    asyncio.run(
        ToolsInstallHandler(
            workflow_name=workflow_name,
            all_workflows=all_workflows,
        ).run()
    )
