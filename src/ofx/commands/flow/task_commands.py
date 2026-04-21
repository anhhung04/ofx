"""CLI commands for listing and inspecting registered tasks.

Registered as a sub-app under ``ofx flow tasks``.
"""

import asyncio
from typing import Annotated

import typer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command("run")
def run_task(
    task_name: Annotated[
        str, typer.Argument(help="Name of the registered task to run (e.g. nmap, httpx, nuclei)")
    ],
    target: Annotated[
        str, typer.Argument(help="Target for the task (IP, domain, URL, or file path)")
    ],
    opt: Annotated[
        list[str] | None,
        typer.Option(
            "--opt",
            "-o",
            help="Task option as key=value or key (boolean flag). Repeatable.",
        ),
    ] = None,
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Execution profile name (applies proxy, threads, rate_limit, etc.).",
        ),
    ] = "",
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help="Timeout in minutes.",
        ),
    ] = 60,
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Directory to store output files.",
        ),
    ] = "",
    store_creds: Annotated[
        bool,
        typer.Option(
            "--store-creds",
            help="Store discovered credentials in the credential store.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output results as JSON.",
        ),
    ] = False,
):
    """Run a single task directly without a workflow YAML.

    \b
    Examples:
      ofx flow tasks run nmap 10.10.10.5 --opt timing=T4
      ofx flow tasks run httpx targets.txt --opt threads=50
      ofx flow tasks run nuclei https://example.com --profile stealth
      ofx flow tasks run subfinder example.com --json
    """
    from ofx.commands.flow.run_task import TaskRunHandler, parse_opt_args

    opts = parse_opt_args(opt or [])
    exit_code = asyncio.run(
        TaskRunHandler(
            task_name=task_name,
            target=target,
            opts=opts,
            profile=profile,
            timeout=timeout,
            output=output,
            store_creds=store_creds,
            json_output=json_output,
        ).run()
    )
    if exit_code:
        raise typer.Exit(exit_code)

@app.command("list")
def list_tasks(
    category: Annotated[
        str,
        typer.Option(
            "-c",
            "--category",
            help="Filter tasks by category prefix (e.g. 'port/', 'url/', 'vuln/').",
        ),
    ] = "",
):
    """List all registered tasks."""
    from rich.table import Table

    from ofx.settings import get_console
    from ofx.tasks import TaskRegistry

    console = get_console()

    if category:
        entries = TaskRegistry.get_by_category(category)
    else:
        entries = [(n, t) for n in TaskRegistry.list_tasks() if (t := TaskRegistry.get(n)) is not None]

    if not entries:
        console.print("[yellow]No tasks found.[/yellow]")
        return

    table = Table(title="Registered Tasks", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Category", style="blue")
    table.add_column("Description", style="white")
    table.add_column("Installed", justify="center")

    for name, task_cls in entries:
        if task_cls is None:
            continue
        task = task_cls()
        installed = task.check_installed()
        status = "[green]✓[/green]" if installed else "[red]✗[/red]"
        table.add_row(name, task.category, task.description, status)

    console.print(table)


@app.command("info")
def task_info(
    task_name: Annotated[str, typer.Argument(help="Name of the task to inspect")],
):
    """Show detailed information about a registered task."""
    from rich.panel import Panel
    from rich.table import Table

    from ofx.settings import get_console
    from ofx.tasks import TaskRegistry

    console = get_console()

    task_cls = TaskRegistry.get(task_name)
    if task_cls is None:
        console.print(f"[red]Task '{task_name}' is not registered.[/red]")
        available = TaskRegistry.list_tasks()
        if available:
            console.print(f"[dim]Available: {', '.join(available)}[/dim]")
        raise typer.Exit(1)

    task = task_cls()

    # Header
    installed = task.check_installed()
    status = "[green]✓ installed[/green]" if installed else "[red]✗ not installed[/red]"
    console.print(
        Panel(
            f"[bold]{task.name}[/bold] — {task.description}\n"
            f"Category: [blue]{task.category}[/blue]  |  Binary: [cyan]{task.cmd}[/cyan]  |  {status}",
            title=f"Task: {task_name}",
            border_style="cyan",
        )
    )

    # Output types
    if task.output_types:
        type_names = ", ".join(t.__name__ for t in task.output_types)
        console.print(f"\n[bold]Output Types:[/bold] {type_names}")

    # Options table
    if task.opts:
        opts_table = Table(
            title="Options", show_header=True, header_style="bold cyan"
        )
        opts_table.add_column("Name", style="green")
        opts_table.add_column("Flag", style="cyan")
        opts_table.add_column("Type", style="blue")
        opts_table.add_column("Description", style="white")

        for opt_name, opt_def in task.opts.items():
            type_str = "flag" if opt_def.is_flag else opt_def.type.__name__
            opts_table.add_row(opt_name, opt_def.flag, type_str, opt_def.help)

        console.print(opts_table)

    # Install command
    if task.install_cmd:
        console.print(f"\n[bold]Install:[/bold] [dim]{task.install_cmd}[/dim]")

    # Capabilities
    caps: list[str] = []
    if task.supports_streaming:
        caps.append("[green]streaming[/green]")
    if task.export_output:
        caps.append("export")
    if task.extra_flags:
        caps.append(f"extra_flags: {' '.join(task.extra_flags)}")
    if task.success_codes != [0]:
        caps.append(f"success_codes: {task.success_codes}")
    if caps:
        console.print(f"\n[bold]Capabilities:[/bold] {', '.join(caps)}")

    # Example YAML
    example_opts = []
    for opt_name, opt_def in list(task.opts.items())[:3]:
        if opt_def.is_flag:
            example_opts.append(f"          {opt_name}: true")
        elif opt_def.type is int:
            example_opts.append(f"          {opt_name}: 100")
        else:
            example_opts.append(f'          {opt_name}: "value"')

    opts_yaml = "\n".join(example_opts)
    console.print(
        f"\n[bold]YAML Example:[/bold]\n"
        f"[dim]    - task: {task_name}\n"
        f"      with:\n"
        f'        target: "{{{{ inputs.target }}}}"\n'
        f"{opts_yaml}[/dim]"
    )
