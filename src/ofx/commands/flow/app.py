import asyncio
from typing import Annotated

import typer

from ofx.commands.flow.collection import app as collection_app
from ofx.commands.flow.profile_commands import app as profile_cmd_app
from ofx.commands.flow.schema import app as schema_app
from ofx.commands.flow.task_commands import app as task_cmd_app
from ofx.commands.project.project_manager import ProjectManager

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(schema_app, name="schema", help="Inspect workflow/job/step model schemas")
app.add_typer(collection_app, name="collection", help="Manage workflow collections")
app.add_typer(task_cmd_app, name="tasks", help="List and inspect registered task wrappers")
app.add_typer(profile_cmd_app, name="profile", help="Manage execution profiles (rate limits, time windows)")

NAME = "flow"

ALIAS = ["x"]

HELP = "Manage and run workflows in the OFX system"


@app.command("list")
def list_workflows():
    """List available workflows from user dirs, built-ins, and installed collections."""
    from pathlib import Path

    from ofx.collections import CollectionManager
    from ofx.collections.manifest import CollectionManifest
    from ofx.commands.ui_helpers import print_warning, status_table
    from ofx.settings import (
        ALLOWED_WORKFLOW_FILE_EXTENSIONS,
        BUILTIN_WORKFLOWS_DIR,
        DEFAULT_WORKFLOWS_DIRS,
        get_console,
    )

    def _scan_yaml_files(root: Path) -> list[Path]:
        files: list[Path] = []
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            files.extend(root.rglob(f"*{ext}"))
        return sorted(set(files))

    rows: list[tuple[str, str, str]] = []
    seen_paths: set[str] = set()

    def _add(path: Path, source: str) -> None:
        resolved = str(path.resolve())
        if resolved in seen_paths:
            return
        seen_paths.add(resolved)
        rows.append((path.stem, source, str(path)))

    # User workflow dirs (cwd + ~/.ofx/workflows)
    for directory in DEFAULT_WORKFLOWS_DIRS:
        if not directory.is_dir():
            continue
        for file in _scan_yaml_files(directory):
            _add(file, "user")

    # Built-in workflows packaged with OFX
    if BUILTIN_WORKFLOWS_DIR.is_dir():
        for subdir in sorted(BUILTIN_WORKFLOWS_DIR.iterdir()):
            if not subdir.is_dir():
                continue
            for file in _scan_yaml_files(subdir):
                _add(file, "builtin")

    # Workflows from installed collections
    manager = CollectionManager()
    for coll_name, entry in manager.list_installed().items():
        coll_path = Path(entry.path)
        if not coll_path.is_dir():
            continue
        manifest = CollectionManifest.from_directory(coll_path)
        if manifest.workflows:
            for workflow in manifest.workflows:
                wf_path = coll_path / workflow
                if wf_path.exists():
                    _add(wf_path, f"collection:{coll_name}")
                else:
                    rows.append((Path(workflow).stem, f"collection:{coll_name}", str(wf_path)))
        else:
            for file in _scan_yaml_files(coll_path):
                _add(file, f"collection:{coll_name}")

    if not rows:
        print_warning("No Workflows Found", "No workflows were discovered in search paths.")
        return

    rows.sort(key=lambda r: (r[1], r[0]))
    table = status_table(
        ("Workflow", "bold cyan"),
        ("Source", "magenta"),
        ("Path", "dim"),
        rows=rows,
    )
    table.title = "Available Workflows"
    get_console().print(table)


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
    events: Annotated[
        bool,
        typer.Option(
            "--events/--no-events",
            help="Emit structured runner lifecycle events to output/events.ndjson.",
        ),
    ] = False,
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
    from ofx.commands import get_cli_env_vars, get_cli_project
    from ofx.commands.flow.run import FlowRunHandler

    # Priority: command --project > global -p > active project
    if not project:
        project = get_cli_project()
    if not project:
        active_path = ProjectManager.get_active_path()
        if active_path:
            project = active_path.name

    asyncio.run(
        FlowRunHandler(
            workflow_name=workflow_name,
            input=input or [],
            env=get_cli_env_vars(),
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
            events=events,
        ).run()
    )


@app.command()
def validate(
    workflow_name: Annotated[
        str, typer.Argument(help="Name of the workflow to validate")
    ] = "",
):
    """Validate a workflow configuration"""
    from ofx.commands.ui_helpers import print_error, print_info, print_success
    from ofx.settings import DEFAULT_WORKFLOWS_DIRS
    from ofx.utils.workflow_utils import find_workflow

    print_info(
        "Workflow Validation",
        f"[bold]Validating:[/bold] [cyan]{workflow_name}[/cyan]",
    )

    try:
        workflow = find_workflow(workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS))
        print_success(
            "Validation Successful",
            f"Workflow '{workflow.name}' is valid!",
            {"Details": "All schema validations passed", "Path": str(workflow.workflow_path)},
        )
    except Exception as e:
        print_error("Validation Error", "Validation failed", str(e))
        raise e


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
