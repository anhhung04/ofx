import asyncio
from typing import Annotated

import typer

from ofx.commands.dump import app as schema_app
from ofx.commands.flow.collection import app as collection_app
from ofx.commands.flow.profile_commands import app as profile_cmd_app
from ofx.commands.flow.task_commands import app as task_cmd_app
from ofx.commands.project.project_manager import ProjectManager

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(schema_app, name="schema", help="Inspect workflow/job/step model schemas")
app.add_typer(collection_app, name="collection", help="Manage workflow collections")
app.add_typer(task_cmd_app, name="tasks", help="List and inspect registered task wrappers")
app.add_typer(profile_cmd_app, name="profile", help="Manage execution profiles (rate limits, time windows)")

NAME = "flow"

ALIAS = []

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
    ] = None,
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
        bool,
        typer.Option(
            "--durable/--no-durable",
            help="Enable or disable durable execution checkpoints.",
        ),
    ] = False,
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
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Suppress interactive console output (cron/headless mode).",
        ),
    ] = False,
    lock: Annotated[
        str,
        typer.Option(
            "--lock",
            help="Optional lock file path to prevent overlapping runs (cron-safe).",
        ),
    ] = "",
    log_format: Annotated[
        str,
        typer.Option(
            "--log-format",
            help="Log format: rich (default), json, or text.",
        ),
    ] = "rich",
    wait_lock: Annotated[
        int,
        typer.Option(
            "--wait-lock",
            help="Seconds to wait for lock acquisition before failing (cron-safe).",
        ),
    ] = 0,
    project: Annotated[
        str,
        typer.Option(
            "-p",
            "--project",
            help="Run workflow for a specific project. Sets output to <project>/logs and exposes project vars.",
        ),
    ] = "",
):
    from ofx.commands.flow.run import FlowRunHandler

    # If no explicit project is supplied, use the active project (if any)
    if not project:
        active_path = ProjectManager.get_active_path()
        if active_path:
            project = active_path.name

    if input is None:
        input = []
    if input is None:
        input = []
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
            quiet=quiet,
            lock=lock,
            log_format=log_format,
            wait_lock=wait_lock,
            project=project,
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
def init(
    workflow_name: Annotated[str, typer.Argument(help="Name of the new workflow")],
    output: Annotated[
        str,
        typer.Option(
            "-o",
            "--output",
            help="Output file path or directory for the new workflow (default: <name>.yml in cwd).",
        ),
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Overwrite the file if it already exists.",
        ),
    ] = False,
):
    """Create a new workflow file pre-configured with YAML language server schema"""
    from ofx.commands.flow.init import FlowInitHandler

    FlowInitHandler().run(workflow_name=workflow_name, output=output, force=force)


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
