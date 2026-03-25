import asyncio
import logging
from typing import Annotated

import typer

from ofx.commands.flow.collection import app as collection_app
from ofx.commands.flow.profile_commands import app as profile_cmd_app
from ofx.commands.flow.schema import app as dump_app
from ofx.commands.flow.task_commands import app as task_cmd_app
from ofx.commands.project.project_manager import ProjectManager

logger = logging.getLogger("ofx")

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(dump_app, name="dump", help="Dumping workflow/job/step model schemas")
app.add_typer(collection_app, name="collection", help="Manage workflow collections")
app.add_typer(task_cmd_app, name="tasks", help="List and inspect registered task wrappers")
app.add_typer(profile_cmd_app, name="profile", help="Manage execution profiles (rate limits, time windows)")

NAME = "flow"

ALIAS = ["x"]

HELP = "Manage and run workflows in the OFX system"


def _complete_workflow_names(incomplete: str) -> list[str]:
    """Shell completion for workflow names (builtin + user + collections)."""
    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS, get_workflow_search_dirs

    names: set[str] = set()

    for d in get_workflow_search_dirs():
        if not d.is_dir():
            continue
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for path in d.rglob(f"*{ext}"):
                stem = path.stem
                if stem.startswith(incomplete):
                    names.add(stem)
                # Also suggest category/name
                try:
                    rel = str(path.relative_to(d).with_suffix(""))
                    if rel.startswith(incomplete):
                        names.add(rel)
                except ValueError:
                    pass

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
                try:
                    data = yaml.safe_load(path.read_text())
                    if isinstance(data, dict):
                        for t in data.get("tags") or []:
                            t_lower = str(t).lower()
                            if t_lower.startswith(incomplete):
                                tags.add(t_lower)
                except Exception:
                    pass
    return sorted(tags)


@app.command("list")
def list_workflows(
    builtin: Annotated[
        bool,
        typer.Option("--builtin", "-b", help="Show only built-in workflows."),
    ] = False,
    collection: Annotated[
        str,
        typer.Option("--collection", "-c", help="Show workflows from a specific installed collection."),
    ] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", "-t", help="Filter workflows by tag. Can be specified multiple times (OR logic).", autocompletion=_complete_tag_names),
    ] = None,
    search: Annotated[
        str,
        typer.Option("--search", "-s", help="Search workflows by name, description, or tags."),
    ] = "",
    show_tags: Annotated[
        bool,
        typer.Option("--tags", help="Show tags alongside each workflow name."),
    ] = False,
    show_descriptions: Annotated[
        bool,
        typer.Option("--descriptions", "-d", help="Show first line of description for each workflow."),
    ] = False,
    list_tags: Annotated[
        bool,
        typer.Option("--list-tags", help="List all available tags with workflow counts."),
    ] = False,
):
    """List available workflows as a folder tree.

    Use --tag/-t to filter by tag, --search/-s to search, --tags to show tags.
    """
    from collections import defaultdict
    from pathlib import Path

    import yaml
    from rich.table import Table
    from rich.tree import Tree

    from ofx.collections import CollectionManager
    from ofx.commands.ui_helpers import print_error, print_warning
    from ofx.settings import (
        ALLOWED_WORKFLOW_FILE_EXTENSIONS,
        BUILTIN_WORKFLOWS_DIR,
        get_console,
    )

    show_all = not builtin and not collection
    filter_tags = {t.lower() for t in tag} if tag else set()
    search_term = search.lower().strip()

    def _scan_yaml_files(root: Path) -> list[Path]:
        files: list[Path] = []
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            files.extend(sorted(root.rglob(f"*{ext}")))
        return sorted(set(files))

    def _read_metadata(path: Path) -> dict:
        """Read name, description, and tags from a workflow YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                tags = data.get("tags", [])
                return {
                    "name": str(data.get("name", path.stem)),
                    "description": str(data.get("description", "")),
                    "tags": [str(t).lower() for t in tags] if isinstance(tags, list) else [],
                }
        except Exception as e:
            logger.debug("Failed to parse workflow metadata from %s: %s", path, e)
            pass
        return {"name": path.stem, "description": "", "tags": []}

    # Collect all files first: (path, source_label, base_root)
    all_files: list[tuple[Path, str, Path]] = []
    seen_paths: set[str] = set()

    def _collect(root: Path, source: str) -> None:
        for file in _scan_yaml_files(root):
            resolved = str(file.resolve())
            if resolved not in seen_paths:
                seen_paths.add(resolved)
                all_files.append((file, source, root))

    # Built-in workflows
    if builtin or show_all:
        if BUILTIN_WORKFLOWS_DIR.is_dir():
            _collect(BUILTIN_WORKFLOWS_DIR, "📦 Built-in")

    # Collection workflows
    if collection or show_all:
        manager = CollectionManager()
        installed = manager.list_installed()

        if collection and collection not in installed:
            print_error(
                "Collection not found",
                f"'{collection}' is not installed.",
                f"Installed: {', '.join(installed) or '(none)'}",
            )
            raise typer.Exit(code=1)

        targets = {collection: installed[collection]} if collection else installed
        for coll_name, entry in targets.items():
            coll_path = Path(entry.path)
            if not coll_path.is_dir():
                continue
            _collect(coll_path, f"📦 {coll_name}")

    console = get_console()

    # --list-tags mode: show all unique tags with counts
    if list_tags:
        tag_counts: dict[str, int] = defaultdict(int)
        for file, _, _ in all_files:
            for t in _read_metadata(file)["tags"]:
                tag_counts[t] += 1

        if not tag_counts:
            print_warning("No Tags Found", "No workflows have tags defined.")
            return

        table = Table(title="Available Tags", show_lines=False, padding=(0, 2))
        table.add_column("Tag", style="cyan bold")
        table.add_column("Workflows", style="white", justify="right")
        for t in sorted(tag_counts, key=lambda x: (-tag_counts[x], x)):
            table.add_row(t, str(tag_counts[t]))
        console.print(table)
        return

    # Read metadata when filtering or showing
    need_metadata = bool(filter_tags) or bool(search_term) or show_tags or show_descriptions
    file_meta: dict[str, dict] = {}
    if need_metadata:
        for file, _, _ in all_files:
            file_meta[str(file.resolve())] = _read_metadata(file)

    # Build grouped tree: source_label -> {category -> [(name, tags, description)]}
    groups: dict[str, dict[str, list[tuple[str, list[str], str]]]] = {}

    for file, source, base_root in all_files:
        resolved = str(file.resolve())
        meta = file_meta.get(resolved, {"name": file.stem, "description": "", "tags": []})
        tags = meta["tags"]
        description = meta["description"]

        # Apply tag filter
        if filter_tags and not filter_tags.intersection(tags):
            continue

        # Apply search filter
        if search_term:
            searchable = f"{file.stem} {meta['name']} {description} {' '.join(tags)}".lower()
            if search_term not in searchable:
                continue

        try:
            category = file.relative_to(base_root).parent
            cat_str = str(category) if str(category) != "." else ""
        except ValueError:
            cat_str = ""
        groups.setdefault(source, defaultdict(list))[cat_str].append((file.stem, tags, description))

    if not groups:
        if filter_tags:
            print_warning("No Workflows Found", f"No workflows matched tags: {', '.join(sorted(filter_tags))}")
        elif search_term:
            print_warning("No Workflows Found", f"No workflows matched search: '{search_term}'")
        else:
            print_warning("No Workflows Found", "No workflows matched the filter.")
        return

    root = Tree("[bold]Available Workflows[/bold]")

    for source_label in sorted(groups):
        categories = groups[source_label]
        source_branch = root.add(f"[bold magenta]{source_label}[/bold magenta]")
        for cat in sorted(categories):
            if cat:
                cat_branch = source_branch.add(f"[yellow]📁 {cat}[/yellow]")
            else:
                cat_branch = source_branch
            for name, tags, description in sorted(categories[cat]):
                parts = [f"[cyan]{name}[/cyan]"]
                if show_tags and tags:
                    parts.append(" ".join(f"[dim]#{t}[/dim]" for t in tags))
                if (show_descriptions or search_term) and description:
                    desc = description.split("\n")[0][:80]
                    parts.append(f"[dim italic]{desc}[/dim italic]")
                cat_branch.add("  ".join(parts))

    console.print(root)


@app.command()
def run(
    workflow_name: Annotated[str, typer.Argument(help="Name of the workflow to run", autocompletion=_complete_workflow_names)],
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
        str, typer.Argument(help="Name of the workflow to validate", autocompletion=_complete_workflow_names)
    ] = "",
    all_workflows: Annotated[
        bool,
        typer.Option("--all", help="Validate all discoverable workflows."),
    ] = False,
    check_tasks: Annotated[
        bool,
        typer.Option("--check-tasks", help="Verify that referenced tasks are registered."),
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
        str, typer.Argument(help="Name of the workflow to lint", autocompletion=_complete_workflow_names)
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
    workflow_name: Annotated[str, typer.Argument(help="Name of the workflow to inspect", autocompletion=_complete_workflow_names)],
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
    workflow_name: Annotated[str, typer.Argument(help="Name of the workflow to visualize", autocompletion=_complete_workflow_names)],
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: terminal (default), dot, json."),
    ] = "terminal",
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Save visualization to file instead of printing."),
    ] = "",
    detailed: Annotated[
        bool,
        typer.Option("--detailed", "-d", help="Show detailed step-level information in boxes."),
    ] = False,
):
    """Visualize workflow dependencies and execution flow as a DAG."""
    from ofx.commands.flow.visualize import visualize

    visualize(workflow_name, format=format, output=output, detailed=detailed)


@app.command()
def history(
    limit: Annotated[
        int,
        typer.Option("-n", "--limit", help="Number of recent runs to show."),
    ] = 20,
    workflow: Annotated[
        str,
        typer.Option("-w", "--workflow", help="Filter by workflow name (substring match)."),
    ] = "",
    status: Annotated[
        str,
        typer.Option("-s", "--status", help="Filter by status: completed, failed, canceled."),
    ] = "",
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Show additional columns (project, jobs, steps)."),
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
        typer.Argument(help="Search term — matches against name, description, and tags"),
    ] = "",
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", "-t", help="Filter by tag. Can be repeated (OR logic).", autocompletion=_complete_tag_names),
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
    from pathlib import Path

    import yaml
    from rich.table import Table

    from ofx.collections import CollectionManager
    from ofx.commands.ui_helpers import print_warning
    from ofx.settings import (
        ALLOWED_WORKFLOW_FILE_EXTENSIONS,
        BUILTIN_WORKFLOWS_DIR,
        get_console,
    )

    console = get_console()
    filter_tags = {t.lower() for t in tag} if tag else set()
    search_term = query.lower().strip()

    if not search_term and not filter_tags:
        print_warning("No Query", "Provide a search term or --tag filter.")
        raise typer.Exit(code=1)

    # Gather all workflow dirs with source labels
    sources: list[tuple[Path, str]] = []
    if BUILTIN_WORKFLOWS_DIR.is_dir():
        sources.append((BUILTIN_WORKFLOWS_DIR, "builtin"))

    user_dir = Path.home() / ".ofx" / "workflows"
    if user_dir.is_dir():
        sources.append((user_dir, "user"))

    manager = CollectionManager()
    for cname, entry in manager.list_installed().items():
        cpath = Path(entry.path)
        if cpath.is_dir():
            sources.append((cpath, f"collection:{cname}"))

    # Scan and filter
    results: list[dict] = []
    seen: set[str] = set()

    for root, source in sources:
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for path in sorted(root.rglob(f"*{ext}")):
                resolved = str(path.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)

                try:
                    data = yaml.safe_load(path.read_text())
                    if not isinstance(data, dict):
                        continue
                except Exception:
                    continue

                name = str(data.get("name", path.stem))
                desc = str(data.get("description", "")).strip()
                tags_list = [str(t).lower() for t in data.get("tags") or [] if t]

                # Tag filter
                if filter_tags and not filter_tags.intersection(tags_list):
                    continue

                # Keyword filter
                if search_term:
                    searchable = f"{path.stem} {name} {desc} {' '.join(tags_list)}".lower()
                    if search_term not in searchable:
                        continue

                try:
                    category = str(path.relative_to(root).parent)
                    if category == ".":
                        category = ""
                except ValueError:
                    category = ""

                results.append({
                    "name": path.stem,
                    "category": category,
                    "description": desc.split("\n")[0][:80] if desc else "",
                    "tags": tags_list,
                    "source": source,
                })

    if not results:
        if search_term and filter_tags:
            print_warning("No Results", f"No workflows matched '{search_term}' with tags: {', '.join(sorted(filter_tags))}")
        elif search_term:
            print_warning("No Results", f"No workflows matched '{search_term}'")
        else:
            print_warning("No Results", f"No workflows matched tags: {', '.join(sorted(filter_tags))}")
        return

    table = Table(title=f"Search Results ({len(results)})", show_lines=False, padding=(0, 1))
    table.add_column("Workflow", style="cyan bold", no_wrap=True)
    table.add_column("Description", style="white")
    if show_tags:
        table.add_column("Tags", style="dim")
    table.add_column("Source", style="dim", no_wrap=True)

    for r in sorted(results, key=lambda x: (x["source"], x["category"], x["name"])):
        wf_name = f"{r['category']}/{r['name']}" if r["category"] else r["name"]
        row = [wf_name, r["description"]]
        if show_tags:
            row.append(", ".join(r["tags"]) if r["tags"] else "")
        row.append(r["source"])
        table.add_row(*row)

    console.print(table)


@app.command("diff")
def diff_cmd(
    workflow_a: Annotated[
        str,
        typer.Argument(help="First workflow name or path", autocompletion=_complete_workflow_names),
    ],
    workflow_b: Annotated[
        str,
        typer.Argument(help="Second workflow name or path", autocompletion=_complete_workflow_names),
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
