import json
import os
import shutil
from datetime import datetime  # For auto-commit
from pathlib import Path
from typing import Optional

import git
import typer
from git.exc import GitCommandError
from rich.console import Console
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

    def add(self, url: str, name: str | None = None) -> tuple[str, Path]:
        if not name:
            name = Path(url).stem

        if name in self.assets:
            raise ValueError(f"Asset collection with name '{name}' already exists.") from None

        target_path = self.workflows_dir / name
        if target_path.exists():
            raise FileExistsError(
                f"Directory '{target_path}' already exists. Please choose a different name."
            )

        console.print(f"Cloning workflow asset collection from [cyan]{url}[/]...")
        try:
            git.Repo.clone_from(url, target_path, depth=1)
        except GitCommandError as e:
            raise RuntimeError(f"Failed to clone repository: {e}") from e

        self.assets[name] = {"url": url, "path": str(target_path)}
        self._save_assets()
        console.print(f"Successfully added asset collection [bold green]'{name}'[/].")
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

            # Ensure local changes are committed before pushing
            self._auto_commit_asset_changes(repo, asset_name)

            origin = repo.remotes.origin
            origin.push()
            console.print(f"  ✅ Pushed local changes for '{asset_name}'.")
        except GitCommandError as e:
            console.print(f"  ❌ Failed to push changes for '{asset_name}': {e}")
        except Exception as e:
            console.print(f"  ❌ An unexpected error occurred while pushing '{asset_name}': {e}")

    def sync(self, name: str | None = None, pull: bool = False, push: bool = False):
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

        for asset_name, details in assets_to_sync.items():
            path = details["path"]
            console.print(f"\n[bold]--- Syncing '{asset_name}' ---[/bold]")

            if pull:
                self._pull_asset(asset_name, path)
            if push:
                self._push_asset(asset_name, path)

            console.print(f"[bold]--- Finished Syncing '{asset_name}' ---[/bold]")

    def remove(self, name: str):
        if name in self.assets:
            path = self.assets[name]["path"]
            console.print(f"Removing asset collection [cyan]'{name}'[/] from [dim]{path}[/]...")
            try:
                shutil.rmtree(path)
                del self.assets[name]
                self._save_assets()
                console.print("✅ Removed successfully.")
            except Exception as e:
                console.print(f"❌ Failed to remove directory: {e}")
        else:
            console.print(f"⚠️ Asset collection '{name}' not found.")


asset_manager = AssetManager()


@app.command()
def init():
    """Initialize the default asset collection if none are installed."""
    if asset_manager.list():
        console.print("⚠️ Asset collections already exist. Skipping initialization.")
        console.print("Use 'ofx asset list' to see them or 'ofx asset add <url>' to add a new one.")
        return

    console.print("No asset collections found. Let's add the default workflow collection.")
    default_url = "https://github.com/anhhung04/ofx-hub.git"
    add_default = typer.confirm(f"Do you want to add the default collection from [cyan]{default_url}[/]?", default=True)

    if add_default:
        try:
            asset_manager.add(default_url, "default")
        except Exception as e:
            console.print(f"❌ Failed to initialize default assets: {e}")


@app.command()
def add(url: str = typer.Argument(..., help="Git URL of the asset collection to add."),
        name: str | None = typer.Option(None, "--name", "-n", help="A custom name for the asset collection.")):
    """Add a new workflow asset collection from a git repository."""
    try:
        asset_manager.add(url, name)
    except (ValueError, FileExistsError, RuntimeError) as e:
        console.print(f"❌ {e}")
        raise typer.Exit(code=1) from e


@app.command("list")
def list_assets():
    """List all installed workflow asset collections."""
    assets = asset_manager.list()
    if not assets:
        console.print("⚠️ No asset collections installed.")
        console.print("Use 'ofx asset add <url>' to add one.")
        return

    table = Table(title="Installed Workflow Asset Collections")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Source URL", style="green")
    table.add_column("Local Path", style="dim")

    for name, details in assets.items():
        table.add_row(name, details["url"], details["path"])

    console.print(table)


@app.command()
def sync(
    name: str | None = typer.Argument(None, help="Name of asset to sync. If none, syncs all."),
    pull: bool = typer.Option(False, "--pull", "-p", help="Pull latest changes from remote."),
    push: bool = typer.Option(False, "--push", "-u", help="Push local changes to remote."),
):
    """Synchronize workflow asset collections with their remote repositories."""
    asset_manager.sync(name, pull, push)


@app.command()
def remove(name: str = typer.Argument(..., help="Name of the asset collection to remove.")):
    """Remove a workflow asset collection."""
    if typer.confirm(f"Are you sure you want to remove the asset collection '{name}'? This will delete the files from your system."):
        asset_manager.remove(name)
    else:
        console.print("Removal cancelled.")
