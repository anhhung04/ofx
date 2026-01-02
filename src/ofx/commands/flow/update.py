from pathlib import Path

import git
import typer

from ofx.settings import DEFAULT_WORKFLOWS_DIR


class UpdateHandler:
    def run(self):
        if len(list(DEFAULT_WORKFLOWS_DIR.glob("*"))) > 0:
            self._update_workflows(DEFAULT_WORKFLOWS_DIR)

    def _update_workflows(self, wf_path: Path):
        want_update = typer.confirm(f"Do you want to update workflows at '{wf_path}'?")
        if not want_update:
            return
        repo = git.Repo(wf_path)
        repo.remotes.origin.pull()
        typer.echo(f"Workflows at '{wf_path}' updated successfully.")
