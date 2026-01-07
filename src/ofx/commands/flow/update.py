from pathlib import Path

import git
import typer
from rich.panel import Panel

from ofx.settings import DEFAULT_WORKFLOWS_DIR, get_console

console = get_console()


class UpdateHandler:
    def run(self):
        if len(list(DEFAULT_WORKFLOWS_DIR.glob("*"))) > 0:
            self._update_workflows(DEFAULT_WORKFLOWS_DIR)

    def _update_workflows(self, wf_path: Path):
        console.print(Panel(
            f"[bold]Location:[/bold] [cyan]{wf_path}[/cyan]",
            title="[~] Update Workflows",
            border_style="cyan"
        ))
        
        want_update = typer.confirm("Do you want to update workflows?")
        if not want_update:
            console.print("[yellow]Update cancelled[/yellow]")
            return
            
        with console.status("[bold green]Updating workflows...", spinner="dots"):
            repo = git.Repo(wf_path)
            repo.remotes.origin.pull()
        
        console.print(Panel(
            f"[bold green]Workflows updated successfully![/bold green]\n"
            f"[dim]Location: {wf_path}[/dim]",
            title="[bold green][OK] Update Complete[/bold green]",
            border_style="green"
        ))
