"""CLI sub-app for ``ofx flow collection`` commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table
from rich.tree import Tree

from ofx.commands.ui_helpers import print_success, print_warning
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def _mgr():
    from ofx.collections.manager import CollectionManager

    return CollectionManager()

# ------------------------------------------------------------------
# add
# ------------------------------------------------------------------


@app.command()
def add(
    name_or_url: Annotated[
        str,
        typer.Argument(
            help="Collection name, org/repo, or full git URL."
        ),
    ],
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Override the local collection name."),
    ] = "",
    ref: Annotated[
        str,
        typer.Option("--ref", "-r", help="Git tag or branch to pin."),
    ] = "",
):
    """Install a workflow collection."""
    mgr = _mgr()
    console = get_console()
    try:
        entry = mgr.add(name_or_url, alias=name, ref=ref)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    print_success(
        "Collection Installed",
        entry.name,
        details={
            "Source": entry.source,
            "Path": str(entry.path),
        },
    )


# ------------------------------------------------------------------
# remove
# ------------------------------------------------------------------


@app.command()
def remove(
    name: Annotated[str, typer.Argument(help="Collection name to remove.")],
):
    """Remove an installed collection."""
    console = get_console()
    if not typer.confirm(f"Remove collection '{name}'? This deletes its files."):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    mgr = _mgr()
    if mgr.remove(name):
        print_success("Removed", f"Collection '{name}' removed.")
    else:
        console.print(f"[yellow]Collection '{name}' not found.[/yellow]")


# ------------------------------------------------------------------
# update
# ------------------------------------------------------------------


@app.command()
def update(
    name: Annotated[
        str,
        typer.Argument(help="Collection to update (omit for all)."),
    ] = "",
):
    """Pull latest changes for installed collections."""
    mgr = _mgr()
    console = get_console()
    updated = mgr.update(name)
    if updated:
        for n in updated:
            console.print(f"[green]Updated:[/green] {n}")
    else:
        console.print("[dim]Nothing to update.[/dim]")


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------
@app.command("list")
def list_collections(
    outdated: Annotated[
        bool,
        typer.Option(
            "--outdated", help="Show only collections with newer remote versions."
        ),
    ] = False,
):
    """List installed collections."""
    mgr = _mgr()
    console = get_console()
    installed = mgr.list_installed()

    if not installed:
        print_warning(
            "Collections",
            "No collections installed.",
            "Use 'ofx flow collection add <name>' to install one.",
        )
        return

    table = Table(
        title=f"Installed Collections ({len(installed)})",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Version", style="green")
    table.add_column("Source", style="dim")
    table.add_column("Tags", style="magenta")

    for name, entry in installed.items():
        table.add_row(
            name,
            entry.version,
            entry.source,
            ", ".join(entry.tags) if entry.tags else "",
        )

    console.print(table)


# ------------------------------------------------------------------
# info
# ------------------------------------------------------------------


@app.command()
def info(
    name: Annotated[str, typer.Argument(help="Collection name.")],
):
    """Show detailed info for an installed collection."""
    from pathlib import Path

    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS

    mgr = _mgr()
    console = get_console()
    entry = mgr.get(name)

    if not entry:
        console.print(f"[yellow]Collection '{name}' not found.[/yellow]")
        raise typer.Exit(code=1)

    tree = Tree(f"[bold cyan]{entry.name}[/bold cyan]")
    if entry.description:
        tree.add(f"[dim]{entry.description}[/dim]")
    tree.add(f"[bold]Source:[/bold] {entry.source}")
    tree.add(f"[bold]Ref:[/bold] {entry.pinned_ref}")
    tree.add(f"[bold]Path:[/bold] [dim]{entry.path}[/dim]")
    tree.add(f"[bold]Installed:[/bold] {entry.installed_at}")

    # Discover workflows from disk
    coll_path = Path(entry.path)
    if coll_path.is_dir():
        workflows: list[str] = []
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            workflows.extend(f.name for f in sorted(coll_path.rglob(f"*{ext}")))
        if workflows:
            wf_node = tree.add(f"[bold]Workflows ({len(workflows)}):[/bold]")
            for wf in sorted(set(workflows)):
                wf_node.add(wf)

    console.print(tree)
