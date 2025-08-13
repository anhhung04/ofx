import git
import typer

from ofx.settings import DEFAULT_WORKFLOWS_DIR
from pathlib import Path


class UpdateHandler:
    def run(self):
        if len(list(DEFAULT_WORKFLOWS_DIR.glob("*"))) > 0:
            self._update_workflows(DEFAULT_WORKFLOWS_DIR)

    def _update_workflows(self, wf_path: Path):
        want_update = typer.confirm(
            f"Do you want to update the workflow configuration at '{wf_path}'?"
        )
        if not want_update:
            return
        try:
            repo = git.Repo(wf_path)
            repo.remotes.origin.pull()
            typer.echo(f"Workflow configuration at '{wf_path}' updated successfully.")
        except git.exc.GitCommandError as e:
            typer.echo(f"Failed to update workflow configuration: {e}")
            return
