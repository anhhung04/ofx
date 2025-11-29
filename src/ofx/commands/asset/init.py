import os
import git
from git.exc import GitCommandError
import typer
import json

from ofx.utils.misc import MetaSingleton
from ofx.settings import DEFAULT_WORKFLOWS_DIR, SECRETS_DIR, settings

from pathlib import Path


class InitHandler(metaclass=MetaSingleton):
    def _write_to_file(self, file_path: str | Path, content: str):
        if isinstance(file_path, str):
            with open(file_path, "w+") as file:
                file.writelines(content)
        else:
            file_path.write_text(content)

    def run(self):
        typer.echo("Unpacking workflows...")
        if not DEFAULT_WORKFLOWS_DIR.exists():
            DEFAULT_WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
        if len(os.listdir(DEFAULT_WORKFLOWS_DIR)) == 0:
            typer.echo(
                f"Workflows will be unpacked to: {DEFAULT_WORKFLOWS_DIR}",
                err=True,
            )
            workflow_git_url = typer.prompt(
                "Enter the git URL of the workflow to unpack", default=""
            )
            if not workflow_git_url:
                typer.echo("No workflow URL provided. Exiting.", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Cloning workflow from {workflow_git_url}...")
            try:
                git.Repo.clone_from(
                    workflow_git_url,
                    DEFAULT_WORKFLOWS_DIR,
                    depth=1,
                )
            except GitCommandError as e:
                typer.echo(f"Failed to clone workflow: {e}", err=True)
                raise typer.Exit(code=1)
        else:
            typer.echo(
                f"Workflows directory '{DEFAULT_WORKFLOWS_DIR}' is not empty. Skipping unpacking.",
                err=True,
            )