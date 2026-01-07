import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

import git
import typer
from git.exc import GitCommandError
from rich.panel import Panel
from rich.table import Table

from ofx.settings import DEFAULT_WORKFLOWS_DIR, get_console

app = typer.Typer()
console = get_console()

NAME = "asset"
HELP = "Manage OFX workflow assets from git repositories."
ASSET_TRACKING_FILE = DEFAULT_WORKFLOWS_DIR.parent / "assets.json"


class AssetManager:
    """Manages workflow asset collections."""

    def __init__(self):
        self.workflows_dir = DEFAULT_WORKFLOWS_DIR
        if not self.workflows_dir.exists():
            self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.assets = self._load_assets()

    def _load_assets(self) -> dict:
        if ASSET_TRACKING_FILE.exists():
            try:
                return json.loads(ASSET_TRACKING_FILE.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_assets(self):
        ASSET_TRACKING_FILE.write_text(json.dumps(self.assets, indent=2))

    def add(self, url: str, name: str = "") -> tuple[str, Path]:
        if not name:
            name = Path(url).stem

        if name in self.assets:
            raise ValueError(f"Asset collection with name '{name}' already exists.") from None

        target_path = self.workflows_dir / name
        if target_path.exists():
            raise FileExistsError(
                f"Directory '{target_path}' already exists. Please choose a different name."
            )

        from rich.panel import Panel
        
        with console.status(f"[bold cyan]Cloning asset collection from {url}...", spinner="dots"):
            try:
                git.Repo.clone_from(url, target_path, depth=1)
            except GitCommandError as e:
                raise RuntimeError(f"Failed to clone repository: {e}") from e

        self.assets[name] = {"url": url, "path": str(target_path)}
        self._save_assets()
        
        console.print(Panel(
            f"[bold]Name:[/bold] [green]{name}[/green]\n"
            f"[bold]Source:[/bold] [cyan]{url}[/cyan]\n"
            f"[bold]Location:[/bold] [dim]{target_path}[/dim]",
            title="[bold green][OK] Asset Collection Added[/bold green]",
            border_style="green"
        ))
        return name, target_path

    def list(self) -> dict:
        return self.assets

    def _auto_commit_asset_changes(self, repo: git.Repo, asset_name: str) -> bool:
        """Auto-commit any local changes in the asset repository."""
        if repo.is_dirty() or repo.untracked_files:
            repo.index.add(repo.untracked_files)
            repo.git.add(A=True)  # Add all changes, including deletions

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hostname = os.getenv("HOSTNAME", "unknown")
            user = os.getenv("USER", "unknown")
            commit_msg = f"Auto-sync asset '{asset_name}': {timestamp} by {user}@{hostname}"

            repo.index.commit(commit_msg)
            console.print(f"  ✅ Auto-committed local changes for '{asset_name}'.")
            return True
        return False

    def _pull_asset(self, asset_name: str, path: str):
        """Performs a git pull for a specific asset."""
        try:
            repo = git.Repo(path)
            if not repo.remotes:
                console.print(f"  ⚠️ Asset '{asset_name}' has no remote configured, skipping pull.")
                return

            origin = repo.remotes.origin
            origin.pull()
            console.print(f"  ✅ Pulled latest changes for '{asset_name}'.")
        except GitCommandError as e:
            console.print(f"  ❌ Failed to pull changes for '{asset_name}': {e}")
        except Exception as e:
            console.print(f"  ❌ An unexpected error occurred while pulling '{asset_name}': {e}")

    def _push_asset(self, asset_name: str, path: str):
        """Performs a git push for a specific asset."""
        try:
            repo = git.Repo(path)
            if not repo.remotes:
                console.print(f"  ⚠️ Asset '{asset_name}' has no remote configured, skipping push.")
                return

            self._auto_commit_asset_changes(repo, asset_name)

            origin = repo.remotes.origin
            origin.push()
            console.print(f"  ✅ Pushed local changes for '{asset_name}'.")
        except GitCommandError as e:
            console.print(f"  ❌ Failed to push changes for '{asset_name}': {e}")
        except Exception as e:
            console.print(f"  ❌ An unexpected error occurred while pushing '{asset_name}': {e}")

    def sync(self, name: str = "", pull: bool = False, push: bool = False):
        assets_to_sync = {}
        if name:
            if name in self.assets:
                assets_to_sync = {name: self.assets[name]}
            else:
                console.print(f"⚠️ Asset collection '{name}' not found.")
                return
        else:
            assets_to_sync = self.assets

        if not assets_to_sync:
            console.print("⚠️ No asset collections installed to sync.")
            return

        if not pull and not push:  # Default behavior is pull if nothing specified
            pull = True

        from rich.panel import Panel
        
        for asset_name, details in assets_to_sync.items():
            path = details["path"]
            
            action = "Pulling" if pull else "Pushing" if push else "Syncing"
            console.print(Panel(
                f"[bold]Asset:[/bold] [cyan]{asset_name}[/cyan]\n"
                f"[bold]Action:[/bold] {action}",
                title="[~] Syncing Asset",
                border_style="cyan"
            ))

            if pull:
                self._pull_asset(asset_name, path)
            if push:
                self._push_asset(asset_name, path)

            console.print(f"[green][OK][/green] Finished syncing [cyan]{asset_name}[/cyan]")

    def remove(self, name: str):
        from rich.panel import Panel
        
        if name in self.assets:
            path = self.assets[name]["path"]
            with console.status(f"[bold red]Removing asset collection '{name}'...", spinner="dots"):
                try:
                    shutil.rmtree(path)
                    del self.assets[name]
                    self._save_assets()
                except Exception as e:
                    console.print(Panel(
                        f"[bold red]Failed to remove directory[/bold red]\n"
                        f"[red]{e}[/red]",
                        title="[X] Error",
                        border_style="red"
                    ))
                    return
            
            console.print(Panel(
                f"[bold green]Asset collection '{name}' removed successfully[/bold green]\n"
                f"[dim]Path: {path}[/dim]",
                title="[OK] Removed",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[yellow]Asset collection '{name}' not found[/yellow]",
                title="[!] Not Found",
                border_style="yellow"
            ))


asset_manager = AssetManager()


@app.command()
def init():
    """Initialize the default asset collection if none are installed."""
    from rich.panel import Panel
    
    if asset_manager.list():
        console.print(Panel(
            "[yellow]Asset collections already exist[/yellow]\n"
            "[dim]Use 'ofx asset list' to view or 'ofx asset add <url>' to add more[/dim]",
            title="[!] Already Initialized",
            border_style="yellow"
        ))
        return

    default_url = "https://github.com/anhhung04/ofx-hub.git"
    console.print(Panel(
        f"[bold]Default collection:[/bold] [cyan]{default_url}[/cyan]\n"
        "[dim]This will download the official OFX workflow collection[/dim]",
        title="[#] Initialize Asset Collections",
        border_style="cyan"
    ))
    
    add_default = typer.confirm("Add the default collection?" , default=True)

    if add_default:
        try:
            asset_manager.add(default_url, "default")
        except Exception as e:
            console.print(Panel(
                f"[bold red]Failed to initialize default assets[/bold red]\n"
                f"[red]{e}[/red]",
                title="[X] Error",
                border_style="red"
            ))


@app.command()
def add(
    url: Annotated[str, typer.Argument(help="Git URL of the asset collection to add.")] = "",
    name: Annotated[
        str,
        typer.Option(
            "--name",
            "-n",
            help="A custom name for the asset collection.",
        ),
    ] = "",
):
    """Add a new workflow asset collection from a git repository."""
    try:
        asset_manager.add(url, name)
    except (ValueError, FileExistsError, RuntimeError) as e:
        console.print(f"❌ {e}")
        raise typer.Exit(code=1) from e


@app.command("list")
def list_assets():
    """List all installed workflow asset collections."""
    from rich.panel import Panel
    
    assets = asset_manager.list()
    if not assets:
        console.print(Panel(
            "[yellow]No asset collections installed[/yellow]\n"
            "[dim]Use 'ofx asset add <url>' to add a collection[/dim]",
            title="[#] Asset Collections",
            border_style="yellow"
        ))
        return

    table = Table(
        title=f"[#] Installed Asset Collections ({len(assets)})",
        border_style="cyan",
        header_style="bold cyan"
    )
    table.add_column("Name", style="cyan bold", no_wrap=True)
    table.add_column("Source URL", style="green")
    table.add_column("Local Path", style="dim")

    for name, details in assets.items():
        table.add_row(name, details["url"], details["path"])

    console.print(table)


@app.command()
def sync(
    name: Annotated[str, typer.Argument(help="Name of asset to sync. If none, syncs all.")] = "",
    pull: Annotated[
        bool,
        typer.Option(
            "--pull",
            "-p",
            help="Pull latest changes from remote.",
        ),
    ] = False,
    push: Annotated[
        bool,
        typer.Option(
            "--push",
            "-u",
            help="Push local changes to remote.",
        ),
    ] = False,
):
    """Synchronize workflow asset collections with their remote repositories."""
    asset_manager.sync(name, pull, push)


@app.command()
def remove(name: Annotated[str, typer.Argument(..., help="Name of the asset collection to remove.")]):
    """Remove a workflow asset collection."""
    if typer.confirm(f"Are you sure you want to remove the asset collection '{name}'? This will delete the files from your system."):
        asset_manager.remove(name)
    else:
        console.print("Removal cancelled.")
