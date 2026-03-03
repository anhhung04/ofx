"""CLI sub-app for ``ofx flow collection`` commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = get_console()


def _mgr():
    from ofx.collections.manager import CollectionManager

    return CollectionManager()


def _index():
    from ofx.collections.index import IndexClient

    return IndexClient()


# ------------------------------------------------------------------
# add
# ------------------------------------------------------------------


@app.command()
def add(
    name_or_url: Annotated[
        str,
        typer.Argument(
            help="Collection name, org/repo, or full git URL. "
            "Bare names resolve to the ofx-workflows GitHub org."
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
    no_deps: Annotated[
        bool,
        typer.Option("--no-deps", help="Skip installing collection dependencies."),
    ] = False,
):
    """Install a workflow collection."""
    mgr = _mgr()
    try:
        entry = mgr.add(name_or_url, alias=name, ref=ref, install_deps=not no_deps)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel(
            f"[bold]Name:[/bold] [green]{entry.name}[/green]\n"
            f"[bold]Version:[/bold] {entry.version}\n"
            f"[bold]Source:[/bold] [cyan]{entry.source}[/cyan]\n"
            f"[bold]Path:[/bold] [dim]{entry.path}[/dim]",
            title="[bold green][OK] Collection Installed[/bold green]",
            border_style="green",
        )
    )


# ------------------------------------------------------------------
# remove
# ------------------------------------------------------------------


@app.command()
def remove(
    name: Annotated[str, typer.Argument(help="Collection name to remove.")],
):
    """Remove an installed collection."""
    if not typer.confirm(
        f"Remove collection '{name}'? This deletes its files."
    ):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    mgr = _mgr()
    if mgr.remove(name):
        console.print(
            Panel(
                f"[green]Collection '{name}' removed.[/green]",
                title="[OK] Removed",
                border_style="green",
            )
        )
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
        typer.Option("--outdated", help="Show only collections with newer remote versions."),
    ] = False,
):
    """List installed collections."""
    mgr = _mgr()
    installed = mgr.list_installed()

    if not installed:
        console.print(
            Panel(
                "[yellow]No collections installed.[/yellow]\n"
                "[dim]Use 'ofx flow collection add <name>' to install one.[/dim]",
                title="Collections",
                border_style="yellow",
            )
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
    mgr = _mgr()
    manifest = mgr.info(name)
    entry = mgr.get(name)

    if not manifest or not entry:
        console.print(f"[yellow]Collection '{name}' not found.[/yellow]")
        raise typer.Exit(code=1)

    tree = Tree(f"[bold cyan]{manifest.name}[/bold cyan] v{manifest.version}")
    if manifest.description:
        tree.add(f"[dim]{manifest.description}[/dim]")
    if manifest.author:
        tree.add(f"[bold]Author:[/bold] {manifest.author}")
    if manifest.license:
        tree.add(f"[bold]License:[/bold] {manifest.license}")
    if manifest.tags:
        tree.add(f"[bold]Tags:[/bold] {', '.join(manifest.tags)}")

    tree.add(f"[bold]Source:[/bold] {entry.source}")
    tree.add(f"[bold]Ref:[/bold] {entry.pinned_ref}")
    tree.add(f"[bold]Path:[/bold] [dim]{entry.path}[/dim]")
    tree.add(f"[bold]Installed:[/bold] {entry.installed_at}")

    if manifest.workflows:
        wf_node = tree.add("[bold]Workflows:[/bold]")
        for wf in manifest.workflows:
            wf_node.add(wf)

    if manifest.tools:
        tool_node = tree.add("[bold]Tools:[/bold]")
        for t in manifest.tools:
            tool_node.add(t)

    if manifest.dependencies:
        dep_node = tree.add("[bold]Dependencies:[/bold]")
        for d in manifest.dependencies:
            label = d.name
            if d.version:
                label += f" {d.version}"
            dep_node.add(label)

    console.print(tree)


# ------------------------------------------------------------------
# search (community index)
# ------------------------------------------------------------------


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search term (name, tag, description).")],
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Force-refresh index from remote."),
    ] = False,
):
    """Search the community collection index."""
    idx = _index()
    results = idx.search(query, force_refresh=refresh)

    if not results:
        console.print(f"[dim]No collections matching '{query}'.[/dim]")
        return

    table = Table(
        title=f"Search Results for '{query}' ({len(results)})",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Latest", style="green")
    table.add_column("Description")
    table.add_column("Tags", style="magenta")

    for entry in results:
        table.add_row(
            entry.name,
            entry.latest,
            entry.description,
            ", ".join(entry.tags) if entry.tags else "",
        )

    console.print(table)
    console.print(
        "\n[dim]Install with:[/dim] ofx flow collection add <name>"
    )


# ------------------------------------------------------------------
# migrate (from legacy assets)
# ------------------------------------------------------------------


@app.command()
def migrate():
    """Migrate legacy asset collections to the new collection system."""
    from ofx.settings import DEFAULT_WORKFLOWS_DIR

    assets_file = DEFAULT_WORKFLOWS_DIR.parent / "assets.json"
    mgr = _mgr()
    count = mgr.migrate_from_assets(assets_file)

    if count:
        console.print(
            Panel(
                f"[green]Migrated {count} collection(s) from legacy assets.[/green]",
                title="[OK] Migration Complete",
                border_style="green",
            )
        )
    else:
        console.print("[dim]No legacy assets to migrate (or already migrated).[/dim]")
