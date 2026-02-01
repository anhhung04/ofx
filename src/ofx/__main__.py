import typer


def main():
    try:
        from ofx.commands import main

        exit_status = main()
    except KeyboardInterrupt:
        exit_status = typer.Exit(code=130)

    return exit_status.exit_code


if __name__ == "__main__":  # pragma: nocover
    import sys

    sys.exit(main())
