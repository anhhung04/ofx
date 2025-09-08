import typer

from typing import Annotated, Optional

app = typer.Typer()

NAME = "project"

HELP = "Manage Red Team projects."


@app.command()
def init(
    base: Annotated[
        str, typer.Option("--base", "-b", help="Base directory for the project")
    ],
    is_multiphase: Annotated[
        bool,
        typer.Option(
            "--multiphase",
            "-m",
            help="Initialize a multi-phase project",
        ),
    ] = False,
    github_url: Annotated[
        Optional[str],
        typer.Option(
            "--git-url",
            "-g",
            help="Remote SCM repository URL to link the project to",
        ),
    ] = None,
):
    """
    Init new OFX project
    """
    from ofx.commands.project.init import InitHandler

    InitHandler(base, is_multiphase, github_url).run()  # type: ignore


@app.command()
def sync(
    project_path: Annotated[
        str,
        typer.Option(
            "--project-path",
            "-p",
            help="Path to the project directory to sync",
        ),
    ],
):
    """
    Sync local project with remote SCM repository
    """
    from ofx.commands.project.sync import SyncProjectHandler

    SyncProjectHandler(project_path).run()
