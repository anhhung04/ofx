import typer

from ofx.commands.ui_helpers import print_banner, print_error

app = typer.Typer(pretty_exceptions_show_locals=False)

from ofx.commands import asset, docs, doctor, dump, flow, project, secret

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


def _register_commands():
    add_app(flow)
    add_app(dump)
    add_app(asset)
    add_app(project)
    add_app(docs)
    add_app(doctor)
    add_app(secret)
    add_aliases()


def main():
    """Main entry point for the OFX CLI application"""
    try:
        _register_commands()
        print_banner()
        app()
    except Exception as e:
        import os
        import traceback

        if os.getenv("OFX_DEBUG"):
            traceback.print_exc()
        print_error("Unhandled Error", str(e))
        return typer.Exit(code=1)
