"""UI helper functions for consistent command output across OFX."""

from __future__ import annotations

from typing import Any, Iterable

from rich import box
from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ofx.settings import get_console

console = get_console()

BANNER_ART = r"""
      .--.
     |o_o |
     |:_/ |
    //   \ \
   (|     | )
  /'\_   _/`\
  \___)=(___/
""".strip("\n")

BANNER_TITLE = "Offensive Flow Executor"
BANNER_TAGLINE = "Handing over to the next generation of red teamers"
BANNER_WIDTH = max(
    max(len(line) for line in BANNER_ART.splitlines()),
    len(BANNER_TITLE),
    len(BANNER_TAGLINE),
)


def _format_details(details: dict[str, Any] | None) -> Text:
    if not details:
        return Text("")
    lines: list[str] = []
    for key, value in details.items():
        lines.append(f"[bold]{key}:[/bold] {value}")
    return Text.from_markup("\n".join(lines))


def banner_panel() -> Group:
    art = Text(BANNER_ART, style="header")
    title = Text(BANNER_TITLE, style="bright")
    tagline = Text(BANNER_TAGLINE, style="dim")
    content = Group(
        Align.center(art, width=BANNER_WIDTH),
        Align.center(title, width=BANNER_WIDTH),
        Align.center(tagline, width=BANNER_WIDTH),
    )
    return content


def print_banner() -> None:
    console.print(banner_panel())


def success_panel(
    title: str, message: str, details: dict[str, Any] | None = None
) -> Panel:
    detail_text = _format_details(details)
    content = Text.from_markup(f"[bold green]{message}[/bold green]")
    if detail_text.plain:
        content.append("\n")
        content.append(detail_text)
    return Panel(
        content,
        title="[bold green][OK] " + title + "[/bold green]",
        border_style="green",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def error_panel(title: str, message: str, details: str | None = None) -> Panel:
    content = f"[bold red]{message}[/bold red]"
    if details:
        content += f"\n[red]{details}[/red]"
    return Panel(
        content,
        title=f"[bold red][X] {title}[/bold red]",
        border_style="red",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def warning_panel(title: str, message: str, hint: str | None = None) -> Panel:
    content = f"[bold yellow]{message}[/bold yellow]"
    if hint:
        content += f"\n[dim]{hint}[/dim]"
    return Panel(
        content,
        title=f"[bold yellow][!] {title}[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def info_panel(
    title: str, message: str, details: dict[str, Any] | None = None
) -> Panel:
    content = Text.from_markup(message)
    detail_text = _format_details(details)
    if detail_text.plain:
        content.append("\n")
        content.append(detail_text)
    return Panel(
        content,
        title=f"[?] {title}",
        border_style="cyan",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def print_success(
    title: str, message: str, details: dict[str, Any] | None = None
) -> None:
    console.print(success_panel(title, message, details))


def print_error(title: str, message: str, details: str | None = None) -> None:
    console.print(error_panel(title, message, details))


def print_warning(title: str, message: str, hint: str | None = None) -> None:
    console.print(warning_panel(title, message, hint))


def print_info(title: str, message: str, details: dict[str, Any] | None = None) -> None:
    console.print(info_panel(title, message, details))


def key_value_table(
    title: str, rows: dict[str, Any] | Iterable[tuple[str, Any]]
) -> Table:
    table = Table(
        title=title,
        show_header=False,
        box=box.SIMPLE,
        border_style="table.border",
        padding=(0, 1),
    )
    table.add_column("Key", style="bold")
    table.add_column("Value", style="white")
    items = rows.items() if isinstance(rows, dict) else rows
    for key, value in items:
        table.add_row(str(key), str(value))
    return table


def inputs_table(inputs: dict[str, Any]) -> Table:
    table = Table(
        title="[bold cyan]Inputs[/bold cyan]",
        show_header=True,
        header_style="bold cyan",
        border_style="dim cyan",
        padding=(0, 1),
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Parameter", style="bold yellow", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Type", style="dim", justify="right")

    for key, value in inputs.items():
        formatted_value, value_type = _format_input_value(value)
        table.add_row(key, formatted_value, value_type)

    return table


def _format_input_value(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return _format_json_value(value), "object"
    if isinstance(value, list):
        return _format_json_value(value), "array"
    if isinstance(value, bool):
        return str(value), "boolean"
    if isinstance(value, (int, float)):
        return str(value), "number"
    return str(value), "string"


def _format_json_value(value: Any) -> str:
    try:
        import json

        return json.dumps(value, indent=2)
    except Exception:
        return str(value)


def workflow_start_panel(
    workflow_name: str, output_path: str, inputs: dict[str, Any] | None = None
) -> Panel:
    content: list[Any] = [
        Text.from_markup(f"[bold cyan]Workflow:[/bold cyan] {workflow_name}"),
        Text.from_markup(f"[bold cyan]Output:[/bold cyan] {output_path}"),
    ]
    if inputs:
        content.append(Text(""))
        content.append(inputs_table(inputs))
    return Panel(
        Group(*content),
        title="[bold green][>] Workflow Execution[/bold green]",
        border_style="green",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def execution_summary_panel(summary: Any) -> Panel:
    data = summary.to_dict() if hasattr(summary, "to_dict") else summary
    totals = (
        f"Jobs: {data.get('total_jobs', 0)} (failed: {data.get('failed_jobs', 0)}) | "
        f"Steps: {data.get('total_steps', 0)} (failed: {data.get('failed_steps', 0)})"
    )
    table = Table(
        show_header=True,
        header_style="table.header",
        border_style="table.border",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Job", style="bold")
    table.add_column("Status", style="white", no_wrap=True)
    table.add_column("Failed Steps", justify="right")
    table.add_column("Error", style="dim", overflow="fold")

    for job in data.get("jobs", []):
        name = job.get("name") or job.get("jid") or "unknown"
        status = job.get("status", "unknown")
        failed_steps = _count_failed_steps(job)
        error = _truncate_text(job.get("error") or "")
        status_color = _status_color(status)
        table.add_row(
            str(name),
            f"[{status_color}]{status}[/{status_color}]",
            str(failed_steps),
            error,
        )

    content = Group(Text.from_markup(f"[bold]Summary:[/bold] {totals}"), table)
    return Panel(
        content,
        title="[bold cyan]Execution Summary[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
        box=box.ROUNDED,
    )


def _count_failed_steps(job: dict[str, Any]) -> int:
    failed_steps = job.get("failed_steps")
    if isinstance(failed_steps, list):
        return len(failed_steps)
    steps = job.get("steps") or []
    return sum(1 for step in steps if step.get("status") == "failed")


def _status_color(status: str) -> str:
    status_map = {
        "completed": "green",
        "failed": "red",
        "canceled": "yellow",
        "running": "cyan",
        "pending": "dim",
    }
    return status_map.get(status, "white")


def _truncate_text(value: str, limit: int = 120) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
