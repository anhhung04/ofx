import typer

from ofx.commands.ui_helpers import print_banner, print_error

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

from ofx.commands import asset, docs, dump, flow, project, secret  # noqa: E402

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



# Global callback to inject environment variables before any command runs
# Store envs parsed from -e
_cli_env_vars = {}

def inject_env_vars(ctx: typer.Context, e: list[str] = typer.Option([], "-e", "--env", help="Inject environment variable (KEY=VAL)", show_default=False)):
    import os
    global _cli_env_vars
    for env in e:
        try:
            key, value = env.split("=", 1)
            os.environ[key] = value
            _cli_env_vars[key] = value
        except ValueError:
            print_error("Invalid environment variable format", f"Expected KEY=VAL, got: {env}")
            raise typer.Exit(code=1)    
    print_banner()

app.callback()(inject_env_vars)


def _register_commands():
    add_app(flow)
    add_app(dump)
    add_app(asset)
    add_app(project)
    add_app(docs)
    add_app(secret)
    add_aliases()


def main():
    """Main entry point for the OFX CLI application"""
    try:
        _register_commands()
        app()
        return typer.Exit(code=0)
    except Exception as e:
        import os
        import traceback

        if os.getenv("OFX_DEBUG"):
            traceback.print_exc()
        print_error("Unhandled Error", str(e))
        return typer.Exit(code=1)
