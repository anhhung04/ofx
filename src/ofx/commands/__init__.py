import typer

from ofx.commands.ui_helpers import error_exit, print_banner

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    invoke_without_command=True,
)

from ofx.commands import (  # noqa: E402
    ai,
    api,
    cloud,
    doctor,
    flow,
    project,
    secret,
    session,
)

COMMAND_ALIASES = {
    flow: ["x"],
    project: ["p"],
}


def add_app(sub_app):
    help = sub_app.HELP
    if hasattr(sub_app, "ALIAS"):
        help = help + f" (alias {', '.join(sub_app.ALIAS)})"
        for alias in sub_app.ALIAS:
            app.add_typer(
                sub_app.app,
                name=alias,
                help=help,
                hidden=True,
            )
    app.add_typer(
        sub_app.app,
        name=sub_app.NAME,
        help=help,
    )


def add_aliases():
    for command_module, aliases in COMMAND_ALIASES.items():
        for alias in aliases:
            app.add_typer(
                command_module.app, name=alias, help=command_module.HELP, hidden=True
            )


# Global callback to inject environment variables and project override
_cli_env_vars: dict[str, str] = {}
_cli_project: str = ""


def get_cli_env_vars() -> dict[str, str]:
    """Return environment variables injected via the global -e/--env flag."""
    return _cli_env_vars


def get_cli_project() -> str:
    """Return project name/path set via the global -p/--project flag."""
    return _cli_project


def inject_env_vars(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit",
        show_default=False,
        is_eager=True,
    ),
    e: list[str] = typer.Option(
        [],
        "-e",
        "--env",
        help="Inject environment variable (KEY=VAL)",
        show_default=False,
    ),
    p: str = typer.Option(
        "",
        "-p",
        "--project",
        help="Override active project for this invocation",
        show_default=False,
    ),
):
    if version:
        from ofx import __version__

        typer.echo(f"ofx {__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

    import os

    from ofx.utils.args import parse_key_value_pairs

    global _cli_env_vars, _cli_project
    try:
        _cli_env_vars = parse_key_value_pairs(e, keep_string=True)
    except ValueError:
        error_exit(
            "Invalid environment variable format",
            "Expected KEY=VAL for each -e flag",
        )

    for key, value in _cli_env_vars.items():
        os.environ[key] = str(value)

    _cli_project = p

    print_banner()


app.callback()(inject_env_vars)


def _register_commands():
    add_app(flow)
    add_app(cloud)
    add_app(session)
    add_app(doctor)
    add_app(project)
    add_app(api)
    add_app(secret)
    add_app(ai)
    add_aliases()


def _clean_up():
    import os
    import shutil

    from ofx.settings import TEMP_DIR

    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def main():
    """Main entry point for the OFX CLI application"""
    try:
        _register_commands()
        app()
        _clean_up()
        return typer.Exit(code=0)
    except Exception as e:
        import os
        import traceback

        if os.getenv("OFX_DEBUG"):
            traceback.print_exc()
        error_exit("Unhandled Error", str(e))
