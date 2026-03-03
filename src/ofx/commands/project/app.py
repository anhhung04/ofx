"""Project management CLI commands."""

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from ofx.settings import get_console

from .encryption import GitFilterHandler
from .handlers import ImportHandler, InitHandler, SyncHandler
from .project_manager import ProjectManager

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = get_console()

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
    console.print(f"[bold green]Creating project '{name}'...[/bold green]")
    base = ProjectManager.create_project(name)

    console.print(f"[bold green]✓[/] Project created: [cyan]{name}[/]")
    console.print(f"[dim]Location: {base}[/]")

    InitHandler.run_interactive(Path(base), is_multiphase)

    console.print(
        Panel(
            f"[bold green]Project '{name}' initialized successfully![/]",
            border_style="green",
            title="[OK] Project Created",
        )
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
        typer.Option("--encryption-key", help="Encryption key (or set OFX_ENCRYPTION_KEY env var)"),
    ] = "",
    message: Annotated[
        str,
        typer.Option("--message", "-m", help="Custom commit message for sync"),
    ] = "",
):
    """Sync local project with remote storage (git by default)"""
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

    console.print(
        Panel(
            f"[bold green]Sync completed successfully![/]\nProject: {project}",
            border_style="green",
            title="[OK] Sync Status",
        )
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
    if not name:
        name = url.split("/")[-1].replace(".git", "")

    console.print(f"[bold blue]⟳[/] Importing project: [cyan]{name}[/]")
    console.print(f"[dim]From: {url}[/]")

    ImportHandler(url, name).run()

    console.print(
        Panel(
            f"[bold green]Project imported successfully![/]\nName: {name}\nURL: {url}",
            border_style="green",
            title="[OK] Import Complete",
        )
    )


@app.command(name="list")
@app.command(name="ls", hidden=True)
def list_projects():
    """List all projects in default project path"""
    projects = ProjectManager.list_projects()

    if not projects:
        console.print(
            Panel(
                "[yellow]No projects found[/yellow]\n"
                f"[dim]Default path: {ProjectManager._get_default_path()}\n"
                "Use 'ofx project init <name>' to create a project[/dim]",
                title="[+] Projects",
                border_style="yellow",
            )
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
    project_path = ProjectManager._get_default_path() / name

    if not project_path.exists():
        console.print(
            Panel(
                f"[bold red]Project '{name}' not found[/bold red]\n"
                "[dim]Use 'ofx project list' to see available projects[/dim]",
                title="[X] Not Found",
                border_style="red",
            )
        )
        return

    console.print(
        Panel(
            f"[bold red]Project:[/bold red] {name}\n"
            f"[bold]Path:[/bold] [dim]{project_path}[/dim]\n\n"
            "[yellow]This action cannot be undone![/yellow]",
            title="[!] Delete Project",
            border_style="red",
        )
    )

    if not typer.confirm("Are you sure you want to delete this project?"):
        console.print("[yellow]Deletion cancelled[/yellow]")
        return

    if ProjectManager.delete_project(name):
        console.print(
            Panel(
                f"[bold green]Project '{name}' deleted successfully[/bold green]",
                title="[OK] Deleted",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]Failed to delete project '{name}'[/bold red]",
                title="[X] Error",
                border_style="red",
            )
        )


@app.command(hidden=True)
def encrypt_filter():
    """Git clean filter: Encrypt stdin to stdout (used by git attributes)"""
    GitFilterHandler.encrypt_stdin_to_stdout()


@app.command(hidden=True)
def decrypt_filter():
    """Git smudge filter: Decrypt stdin to stdout (used by git attributes)"""
    GitFilterHandler.decrypt_stdin_to_stdout()
