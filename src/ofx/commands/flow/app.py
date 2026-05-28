import asyncio
import enum
import logging
from contextlib import suppress
from typing import Annotated

import typer

from ofx.commands.flow.checkpoint import app as checkpoint_app
from ofx.commands.flow.collection import app as collection_app
from ofx.commands.flow.profile_commands import app as profile_cmd_app
from ofx.commands.flow.schema import app as dump_app
from ofx.commands.flow.task_commands import app as task_cmd_app
from ofx.commands.project.project_manager import ProjectManager

logger = logging.getLogger("ofx")


class VisualizeFormat(str, enum.Enum):
    terminal = "terminal"
    dot = "dot"
    json = "json"


app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(dump_app, name="dump", help="Dumping workflow/job/step model schemas")
app.add_typer(collection_app, name="collection", help="Manage workflow collections")
app.add_typer(
    checkpoint_app, name="checkpoint", help="Manage durable execution checkpoints"
)
app.add_typer(
    task_cmd_app, name="tasks", help="List and inspect registered task wrappers"
)
app.add_typer(
    profile_cmd_app,
    name="profile",
    help="Manage execution profiles (rate limits, time windows)",
)

NAME = "flow"

ALIAS = ["x"]

HELP = "Manage and run workflows in the OFX system"


def _complete_workflow_names(incomplete: str) -> list[str]:
    """Shell completion for workflow names, with directory-aware segmented completion.

    Supports ``category/name`` style workflow names by completing one path
    segment at a time (like file-path completion), which avoids shell
    issues with ``/`` inside completion values.
    """
    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS, get_workflow_search_dirs

    # Normalise backslash to forward-slash so Windows paths work too
    incomplete = incomplete.replace("\\", "/")

    # Split into directory prefix and leaf incomplete part
    if "/" in incomplete:
        prefix, _leaf = incomplete.rsplit("/", 1)
    else:
        prefix, _leaf = "", incomplete

    names: set[str] = set()

    for d in get_workflow_search_dirs():
        if not d.is_dir():
            continue
        search_root = d / prefix if prefix else d

        if not search_root.is_dir():
            continue

        # Offer immediate children: subdirectories (with trailing /)
        # and workflow files (stem only)
        for child in search_root.iterdir():
            if child.name.startswith(".") or child.name.startswith("__"):
                continue
            rel_prefix = f"{prefix}/" if prefix else ""
            if child.is_dir():
                # Only suggest directories that contain workflow files
                has_workflows = any(
                    f.suffix in ALLOWED_WORKFLOW_FILE_EXTENSIONS
                    for f in child.rglob("*")
                    if f.is_file()
                )
                if not has_workflows:
                    continue
                dirname = f"{rel_prefix}{child.name}/"
                if dirname.startswith(incomplete):
                    names.add(dirname)
            elif child.is_file() and child.suffix in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
                wf_name = f"{rel_prefix}{child.stem}"
                if wf_name.startswith(incomplete):
                    names.add(wf_name)

    return sorted(names)


def _complete_tag_names(incomplete: str) -> list[str]:
    """Shell completion for workflow tags."""
    import yaml

    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS, get_workflow_search_dirs

    tags: set[str] = set()
    for d in get_workflow_search_dirs():
        if not d.is_dir():
            continue
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for path in d.rglob(f"*{ext}"):
                with suppress(Exception):
                    data = yaml.safe_load(path.read_text())
                    if isinstance(data, dict):
                        for t in data.get("tags") or []:
                            t_lower = str(t).lower()
                            if t_lower.startswith(incomplete):
                                tags.add(t_lower)
    return sorted(tags)


@app.command("list")
def list_workflows(
    builtin: Annotated[
        bool,
        typer.Option("--builtin", "-b", help="Show only built-in workflows."),
    ] = False,
    collection: Annotated[
        str,
        typer.Option(
            "--collection",
            "-c",
            help="Show workflows from a specific installed collection.",
        ),
    ] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            "-t",
            help="Filter workflows by tag. Can be specified multiple times (OR logic).",
            autocompletion=_complete_tag_names,
        ),
    ] = None,
    search: Annotated[
        str,
        typer.Option(
            "--search", "-s", help="Search workflows by name, description, or tags."
        ),
    ] = "",
    show_tags: Annotated[
        bool,
        typer.Option("--tags", help="Show tags alongside each workflow name."),
    ] = False,
    show_descriptions: Annotated[
        bool,
        typer.Option(
            "--descriptions",
            "-d",
            help="Show first line of description for each workflow.",
        ),
    ] = False,
    list_tags: Annotated[
        bool,
        typer.Option(
            "--list-tags", help="List all available tags with workflow counts."
        ),
    ] = False,
):
    """List available workflows as a folder tree.

    Use --tag/-t to filter by tag, --search/-s to search, --tags to show tags.
    """
    from ofx.commands.flow.list_cmd import show_list

    filter_tags = {t.lower() for t in tag} if tag else set()

    show_list(
        builtin=builtin,
        collection=collection,
        filter_tags=filter_tags,
        search_term=search.lower().strip(),
        show_tags=show_tags,
        show_descriptions=show_descriptions,
        list_tags=list_tags,
    )


@app.command()
def run(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to run", autocompletion=_complete_workflow_names
        ),
    ],
    input: Annotated[
        list[str] | None,
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
    auto_commit: Annotated[
        bool,
        typer.Option(
            "--auto-commit",
            help="Auto-commit output directory to git after workflow completion.",
        ),
    ] = False,
    auto_push: Annotated[
        bool,
        typer.Option(
            "--auto-push",
            help="Auto-push committed data to git remote (implies --auto-commit).",
        ),
    ] = False,
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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show execution plan without running (jobs, stages, inputs, dependencies).",
        ),
    ] = False,
    time_window: Annotated[
        str,
        typer.Option(
            "--time-window",
            help="Restrict execution to a time window (HH:MM-HH:MM, e.g. '09:00-17:00').",
        ),
    ] = "",
    load_targets: Annotated[
        bool,
        typer.Option(
            "-T",
            "--load-targets",
            help="Load targets from project targets/ folder and expand as matrix input.",
        ),
    ] = False,
):
    if dry_run:
        from ofx.commands.flow.info import show_info

        show_info(workflow_name, detailed=True)
        return

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
            auto_commit=auto_commit,
            auto_push=auto_push,
            quiet=quiet,
            lock=lock,
            log_format=log_format,
            wait_lock=wait_lock,
            project=project,
            events=events,
            time_window=time_window,
            load_targets=load_targets,
        ).run()
    )


@app.command()
def validate(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to validate",
            autocompletion=_complete_workflow_names,
        ),
    ] = "",
    all_workflows: Annotated[
        bool,
        typer.Option("--all", help="Validate all discoverable workflows."),
    ] = False,
    check_tasks: Annotated[
        bool,
        typer.Option(
            "--check-tasks", help="Verify that referenced tasks are registered."
        ),
    ] = False,
):
    """Validate workflow configuration with detailed diagnostics.

    Reports schema validity, structure summary, and optionally checks task references.
    Use --all to bulk-validate every discoverable workflow.
    """
    from ofx.commands.flow.validate import validate_workflows

    validate_workflows(
        workflow_name=workflow_name,
        all_workflows=all_workflows,
        check_tasks=check_tasks,
    )


@app.command()
def lint(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to lint", autocompletion=_complete_workflow_names
        ),
    ] = "",
    all_workflows: Annotated[
        bool,
        typer.Option("--all", help="Lint all discoverable workflows."),
    ] = False,
):
    """Check workflows for best-practice issues (descriptions, tags, naming, timeouts)."""
    from ofx.commands.flow.lint import lint_workflows

    lint_workflows(all_workflows=all_workflows, workflow_name=workflow_name)


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
def info(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to inspect",
            autocompletion=_complete_workflow_names,
        ),
    ],
    detailed: Annotated[
        bool,
        typer.Option("--detailed", "-d", help="Show detailed step-level information."),
    ] = False,
):
    """Display detailed information about a workflow (inputs, jobs, outputs, execution plan)."""
    from ofx.commands.flow.info import show_info

    show_info(workflow_name, detailed=detailed)


@app.command("visualize")
def visualize_cmd(
    workflow_name: Annotated[
        str,
        typer.Argument(
            help="Name of the workflow to visualize",
            autocompletion=_complete_workflow_names,
        ),
    ],
    format: Annotated[
        VisualizeFormat,
        typer.Option(
            "--format", "-f", help="Output format: terminal (default), dot, json."
        ),
    ] = VisualizeFormat.terminal,
    output: Annotated[
        str,
        typer.Option(
            "--output", "-o", help="Save visualization to file instead of printing."
        ),
    ] = "",
    detailed: Annotated[
        bool,
        typer.Option(
            "--detailed", "-d", help="Show detailed step-level information in boxes."
        ),
    ] = False,
):
    """Visualize workflow dependencies and execution flow as a DAG."""
    from ofx.commands.flow.visualize import visualize

    visualize(workflow_name, format=format.value, output=output, detailed=detailed)


@app.command()
def history(
    limit: Annotated[
        int,
        typer.Option("-n", "--limit", help="Number of recent runs to show."),
    ] = 20,
    workflow: Annotated[
        str,
        typer.Option(
            "-w", "--workflow", help="Filter by workflow name (substring match)."
        ),
    ] = "",
    status: Annotated[
        str,
        typer.Option(
            "-s", "--status", help="Filter by status: completed, failed, canceled."
        ),
    ] = "",
    verbose: Annotated[
        bool,
        typer.Option(
            "-v", "--verbose", help="Show additional columns (project, jobs, steps)."
        ),
    ] = False,
    clear: Annotated[
        bool,
        typer.Option("--clear", help="Clear all run history."),
    ] = False,
    prune: Annotated[
        int,
        typer.Option("--prune", help="Prune history to keep only the last N entries."),
    ] = 0,
):
    """Show past workflow run history."""
    from ofx.commands.flow.history import clear_history, prune_history, show_history
    from ofx.commands.ui_helpers import print_info
    from ofx.settings import get_console

    if clear:
        count = clear_history()
        print_info("History Cleared", f"Removed {count} run record(s).")
        return

    if prune > 0:
        count = prune_history(keep=prune)
        if count:
            print_info("History Pruned", f"Removed {count} oldest record(s).")
        else:
            get_console().print("[dim]Nothing to prune.[/dim]")
        return

    show_history(limit=limit, workflow=workflow, status=status, verbose=verbose)


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


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(
            help="Search term — matches against name, description, and tags"
        ),
    ] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            "-t",
            help="Filter by tag. Can be repeated (OR logic).",
            autocompletion=_complete_tag_names,
        ),
    ] = None,
    show_tags: Annotated[
        bool,
        typer.Option("--tags", help="Show tags alongside each result."),
    ] = False,
):
    """Search workflows by keyword, name, description, or tag.

    Searches across built-in workflows, user workflows, and installed collections.

    \b
    Examples:
      ofx flow search recon
      ofx flow search --tag web
      ofx flow search nmap --tags
      ofx flow search --tag vuln --tag scan
    """
    from ofx.commands.ui_helpers import print_warning

    filter_tags = {t.lower() for t in tag} if tag else set()

    if not query.strip() and not filter_tags:
        print_warning("No Query", "Provide a search term or --tag filter.")
        raise typer.Exit(code=1)

    from ofx.commands.flow.search_cmd import show_search

    show_search(query=query, filter_tags=filter_tags, show_tags=show_tags)


@app.command("diff")
def diff_cmd(
    workflow_a: Annotated[
        str,
        typer.Argument(
            help="First workflow name or path", autocompletion=_complete_workflow_names
        ),
    ],
    workflow_b: Annotated[
        str,
        typer.Argument(
            help="Second workflow name or path", autocompletion=_complete_workflow_names
        ),
    ],
):
    """Compare two workflows and show structural differences.

    \b
    Examples:
      ofx flow diff host-scan port-blitz
      ofx flow diff recon/subdomain-recon recon/full-recon
    """
    from ofx.commands.flow.diff import show_diff

    show_diff(workflow_a, workflow_b)
