from pathlib import Path

import git
import typer

from ofx.commands.ui_helpers import print_info, print_success, print_warning
from ofx.settings import DEFAULT_WORKFLOWS_DIR


class UpdateHandler:
    def run(self):
        if len(list(DEFAULT_WORKFLOWS_DIR.glob("*"))) > 0:
            self._update_workflows(DEFAULT_WORKFLOWS_DIR)

    def _update_workflows(self, wf_path: Path):
        print_info(
            "Update Workflows",
            f"[bold]Location:[/bold] [cyan]{wf_path}[/cyan]",
        )

        want_update = typer.confirm("Do you want to update workflows?")
        if not want_update:
            print_warning("Update Cancelled", "No changes were made.")
            return

        print_info("Updating Workflows", "[bold green]Pulling latest changes...[/bold green]")
        repo = git.Repo(wf_path)
        repo.remotes.origin.pull()

        print_success(
            "Update Complete",
            "Workflows updated successfully!",
            {"Location": wf_path},
        )
