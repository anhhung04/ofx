"""Project management CLI commands."""

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.ui_helpers import print_error, print_success, print_warning
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "project"
HELP = "Manage Red Team projects."


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Project name")],
    is_multiphase: Annotated[
        bool,
        typer.Option("--multiphase", "-m", help="Initialize a multi-phase project"),
    ] = False,
):
    """Init new OFX project"""
    console = get_console()
    from .handlers.init import InitHandler
    from .project_manager import ProjectManager

    console.print(f"[bold green]Creating project '{name}'...[/bold green]")
    base = ProjectManager.create_project(name)
    InitHandler.run_interactive(Path(base), is_multiphase)

    print_success(
        "Project Created",
        f"Project '{name}' initialized successfully!",
        details={"Location": base},
    )


@app.command()
def sync(
    project: Annotated[str, typer.Argument(help="Project name or path")],
    remote_type: Annotated[
        str,
        typer.Option("--remote-type", "-t", help="Remote storage type: git or ssh"),
    ] = "git",
    remote_config: Annotated[
        str,
        typer.Option("--remote-config", "-c", help="Remote config as JSON"),
    ] = "",
    encrypt: Annotated[
        bool,
        typer.Option("--encrypt", "-e", help="Encrypt files before syncing"),
    ] = False,
    encryption_key: Annotated[
        str,
        typer.Option(
            "--encryption-key",
            help="Encryption key (or set OFX_ENCRYPTION_KEY env var)",
        ),
    ] = "",
    message: Annotated[
        str,
        typer.Option("--message", "-m", help="Custom commit message for sync"),
    ] = "",
):
    """Sync local project with remote storage (git by default)"""
    console = get_console()
    from .handlers.sync import SyncHandler
    from .project_manager import ProjectManager

    path = ProjectManager.resolve_path(project)

    console.print(f"[bold blue]⟳[/] Preparing sync for project: [cyan]{project}[/]")
    console.print(f"[dim]Remote type: {remote_type}[/]")
    if encrypt:
        console.print("[dim]Encryption: enabled[/]")

    with console.status("[bold green]Syncing...[/]", spinner="dots"):
        SyncHandler(
            path,
            remote_type=remote_type,
            remote_config=remote_config,
            encrypt=encrypt,
            encryption_key=encryption_key,
            message=message,
        ).run()

    print_success(
        "Sync Status",
        "Sync completed successfully!",
        details={"Project": project},
    )


@app.command(name="import")
def import_project(
    url: Annotated[str, typer.Argument(help="Git repository URL to clone")],
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Custom name for the imported project"),
    ] = "",
):
    """Import project by cloning from remote git repository"""
    console = get_console()
    from .handlers.import_ import ImportHandler

    if not name:
        name = url.split("/")[-1].replace(".git", "")

    console.print(f"[bold blue]⟳[/] Importing project: [cyan]{name}[/]")
    console.print(f"[dim]From: {url}[/]")

    ImportHandler(url, name).run()

    print_success(
        "Import Complete",
        "Project imported successfully!",
        details={"Name": name, "URL": url},
    )


@app.command(name="list")
@app.command(name="ls", hidden=True)
def list_projects():
    """List all projects in default project path"""
    console = get_console()
    from .project_manager import ProjectManager

    projects = ProjectManager.list_projects()

    if not projects:
        print_warning(
            "Projects",
            "No projects found",
            hint=(
                f"Default path: {ProjectManager._get_default_path()}\n"
                "Use 'ofx project init <name>' to create a project"
            ),
        )
        return

    table = Table(
        title=f"[+] OFX Projects ({len(projects)})",
        show_header=True,
        header_style="bold cyan",
        expand=True,
        border_style="cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Project Name", style="cyan")
    table.add_column("Path", style="dim")

    for idx, p in enumerate(projects, 1):
        full_path = ProjectManager._get_default_path() / p
        table.add_row(str(idx), p, str(full_path))

    console.print(table)


@app.command(name="remove")
@app.command(name="rm", hidden=True)
def remove(name: Annotated[str, typer.Argument(help="Project name to delete")]):
    """Remove a project by name"""
    from .project_manager import ProjectManager

    project_path = ProjectManager._get_default_path() / name

    if not project_path.exists():
        print_error(
            "Project Not Found",
            f"Project '{name}' not found",
            details="Use 'ofx project list' to see available projects",
        )
        return

    print_warning(
        "Delete Project",
        f"Project: {name}",
        hint=f"Path: {project_path}\nThis action cannot be undone!",
    )

    if not typer.confirm("Are you sure you want to delete this project?"):
        get_console().print("[yellow]Deletion cancelled[/yellow]")
        return

    if ProjectManager.delete_project(name):
        print_success(
            "Deleted",
            f"Project '{name}' deleted successfully",
            details={"Name": name, "Path": str(project_path)},
        )
    else:
        print_error(
            "Delete Failed",
            f"Failed to delete project '{name}'",
        )


@app.command(name="use")
def use(
    name: Annotated[str, typer.Argument(help="Project name or path (empty when clearing)")] = "",
    clear: Annotated[bool, typer.Option("--clear", "-c", help="Clear the active project setting")] = False,
):
    """Set or clear the active/working project."""
    console = get_console()
    from .project_manager import ProjectManager, _load_config, _save_config
    if clear:
        cfg = _load_config()
        cfg.pop("active_project", None)
        _save_config(cfg)
        # Also clear environment variable and Settings field
        os.environ.pop("OFX_ACTIVE_PROJECT", None)
        from ofx.settings import settings
        settings.active_project = None
        console.print("[yellow]Active project cleared.[/]")
        return
    if not name:
        console.print("[red]Provide a project name/path or use --clear.[/]")
        raise typer.Exit(code=1)
    resolved = ProjectManager.resolve_path(name)
    if not Path(resolved).exists():
        console.print(f"[red]Project '{name}' not found at {resolved}[/]")
        raise typer.Exit(code=1)
    cfg = _load_config()
    cfg["active_project"] = name
    _save_config(cfg)
    # Export to env var and Settings for this and downstream processes
    os.environ["OFX_ACTIVE_PROJECT"] = name
    from ofx.settings import settings
    settings.active_project = name
    console.print(f"[green]Active project set to:[/] {name} → {resolved}")

@app.command()
def status(
    name: Annotated[
        str,
        typer.Argument(
            help="Project name or path (defaults to active project)",
        ),
    ] = "",
):
    """Show project status and directory summary."""
    console = get_console()
    from .project_manager import ProjectManager

    if not name:
        active = ProjectManager.get_active_path()
        if not active:
            print_error(
                "No Project",
                "No active project set",
                details="Use 'ofx project use <name>' or pass a project name",
            )
            raise typer.Exit(code=1)
        project_path = active
    else:
        project_path = Path(ProjectManager.resolve_path(name))

    if not project_path.exists():
        print_error("Not Found", f"Project not found: {project_path}")
        raise typer.Exit(code=1)

    from rich.panel import Panel
    from rich.text import Text

    # Count files in key directories
    dir_stats: list[tuple[str, int]] = []
    key_dirs = [
        "hosts", "subdomains", "vulns", "web", "certs", "osint",
        "evidence", "scans", "scope", "targets", "tools", "exploits",
        "logs", "post-exploits",
    ]
    for d in key_dirs:
        dp = project_path / d
        if dp.is_dir():
            count = sum(1 for f in dp.rglob("*") if f.is_file() and f.name != ".gitkeep")
            if count > 0:
                dir_stats.append((d, count))

    # Disk usage
    total_bytes = sum(f.stat().st_size for f in project_path.rglob("*") if f.is_file())
    if total_bytes > 1_048_576:
        size_str = f"{total_bytes / 1_048_576:.1f} MB"
    elif total_bytes > 1024:
        size_str = f"{total_bytes / 1024:.1f} KB"
    else:
        size_str = f"{total_bytes} B"

    # Git info
    git_info = ""
    try:
        import git as gitlib

        try:
            repo = gitlib.Repo(project_path)
            branch = repo.active_branch.name
            dirty = repo.is_dirty()
            status_str = "[red]dirty[/]" if dirty else "[green]clean[/]"
            last_commit = ""
            if repo.head.is_valid():
                commit = repo.head.commit
                last_commit = f" — last commit: {commit.committed_datetime.strftime('%Y-%m-%d %H:%M')}"
            git_info = f"  [dim]Git:[/] {branch} ({status_str}){last_commit}"
        except gitlib.exc.InvalidGitRepositoryError:
            git_info = "  [dim]Git:[/] not initialized"
        except Exception:
            git_info = "  [dim]Git:[/] error reading status"
    except ImportError:
        git_info = "  [dim]Git:[/] [yellow]GitPython not installed[/]"

    # Build display
    lines = [
        f"  [bold]Project:[/] {project_path.name}",
        f"  [dim]Path:[/] {project_path}",
        f"  [dim]Size:[/] {size_str}",
        git_info,
        "",
    ]

    if dir_stats:
        lines.append("  [bold cyan]Findings:[/]")
        for dirname, count in sorted(dir_stats, key=lambda x: -x[1]):
            bar = "█" * min(count, 30)
            lines.append(f"    {dirname:<16} {count:>5}  [green]{bar}[/]")
    else:
        lines.append("  [dim]No findings yet — run a scan workflow![/]")

    panel = Panel(
        Text.from_markup("\n".join(lines)),
        title="[bold]Project Status[/]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


@app.command(hidden=True)
def encrypt_filter():
    """Git clean filter: Encrypt stdin to stdout (used by git attributes)"""
    from .encryption import GitFilterHandler

    GitFilterHandler.encrypt_stdin_to_stdout()


@app.command(hidden=True)
def decrypt_filter():
    """Git smudge filter: Decrypt stdin to stdout (used by git attributes)"""
    from .encryption import GitFilterHandler

    GitFilterHandler.decrypt_stdin_to_stdout()
