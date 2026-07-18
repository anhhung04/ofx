"""Format typed task outputs as rich tables for terminal display."""

from __future__ import annotations

from collections import Counter
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_TYPE_COLUMNS: dict[str, list[tuple[str, str, str, int | None]]] = {
    "port": [
        ("ip", "Host", "bold", None),
        ("port", "Port", "cyan bold", None),
        ("protocol", "Proto", "dim", 5),
        ("state", "State", "", 8),
        ("service_name", "Service", "green", 20),
    ],
    "url": [
        ("url", "URL", "cyan", 60),
        ("status_code", "Status", "bold", 6),
        ("title", "Title", "", 40),
        ("tech", "Tech", "magenta", 30),
    ],
    "subdomain": [
        ("host", "Subdomain", "cyan", 50),
        ("domain", "Domain", "dim", 30),
        ("sources", "Sources", "magenta", 30),
    ],
    "vulnerability": [
        ("severity", "Sev", "", 8),
        ("name", "Name", "bold", 40),
        ("matched_at", "Target", "cyan", 40),
        ("id", "ID", "dim", 20),
    ],
    "record": [
        ("type", "Type", "bold cyan", 8),
        ("name", "Record", "", 50),
        ("host", "Host", "dim", 30),
    ],
    "ip": [
        ("ip", "IP", "cyan bold", None),
        ("host", "Host", "", 40),
        ("protocol", "Proto", "dim", 6),
    ],
    "domain": [
        ("domain", "Domain", "cyan bold", None),
        ("registrar", "Registrar", "", 30),
        ("creation_date", "Created", "dim", 12),
        ("expiration_date", "Expires", "dim", 12),
    ],
    "tag": [
        ("name", "Tag", "bold", 30),
        ("value", "Value", "cyan", 40),
        ("category", "Category", "magenta", 15),
    ],
    "certificate": [
        ("host", "Host", "bold", 30),
        ("subject_cn", "CN", "cyan", 30),
        ("issuer_cn", "Issuer", "", 30),
        ("not_after", "Expires", "dim", 12),
        ("self_signed", "Self-Signed", "red", 10),
    ],
    "exploit": [
        ("name", "Exploit", "bold", 50),
        ("provider", "Source", "magenta", 12),
        ("id", "ID", "cyan", 20),
    ],
    "user_account": [
        ("username", "User", "bold cyan", 20),
        ("domain", "Domain", "", 20),
        ("host", "Host", "", 20),
        ("privilege_level", "Privilege", "magenta", 12),
    ],
}

_SEVERITY_STYLES = {
    "critical": "bold white on red",
    "high": "bold red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
    "unknown": "dim",
}

_STATUS_CODE_STYLES = {2: "green", 3: "yellow", 4: "red", 5: "bold red"}

def _summary_label(key: str, value: int) -> str:
    if value == 1:
        return key
    if key.endswith("s"):
        return key + "es"
    return key + "s"

def _display_output_value(value: Any) -> str:
    if value is None or value == "" or value == 0:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value[:5]) + (
            "…" if len(value) > 5 else ""
        )
    if isinstance(value, bool):
        return "✓" if value else ""
    return str(value)

def _contextual_cell_style(field: str, value: Any, default_style: str) -> str:
    if field == "severity":
        return _SEVERITY_STYLES.get(str(value or "").lower(), default_style)
    if field == "status_code" and isinstance(value, int) and value > 0:
        return _STATUS_CODE_STYLES.get(value // 100, default_style)
    return default_style

def format_typed_outputs(
    typed_outputs: list[dict[str, Any]],
    task_name: str = "",
    console: Console | None = None,
) -> None:
    """Render typed task outputs as rich tables to the console."""
    if not typed_outputs:
        return

    console = console or Console()

    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in typed_outputs:
        output_type = item.get("_type", "unknown")
        by_type.setdefault(output_type, []).append(item)

    renderables: list[Any] = []
    for type_name, items in by_type.items():
        columns = _TYPE_COLUMNS.get(type_name)
        if not columns:
            renderables.append(Text(f"  {type_name}: {len(items)} item(s)", style="dim"))
            continue

        table = Table(
            show_header=True,
            header_style="bold",
            show_lines=False,
            pad_edge=False,
            expand=False,
        )
        for _, header, style, max_width in columns:
            table.add_column(
                header,
                style=style,
                max_width=max_width,
                no_wrap=max_width is not None,
            )

        prepared_rows: list[list[str | Text]] = []
        for item in items:
            row: list[str | Text] = []
            has_value = False
            for field, _, style, _ in columns:
                value = item.get(field)
                display_value = _display_output_value(value)

                if display_value:
                    has_value = True

                cell_style = _contextual_cell_style(field, value, style)

                row.append(
                    Text(display_value, style=cell_style)
                    if cell_style != style
                    else display_value
                )

            if has_value:
                prepared_rows.append(row)

        if not prepared_rows:
            continue

        max_rows = 50
        for row in prepared_rows[:max_rows]:
            table.add_row(*row)

        if len(prepared_rows) > max_rows:
            table.add_row(
                *[
                    f"… +{len(prepared_rows) - max_rows} more" if index == 0 else ""
                    for index in range(len(columns))
                ]
            )

        renderables.append(table)

    if not renderables:
        return

    counts = Counter(item.get("_type", "?") for item in typed_outputs)
    summary_parts = []
    for key, value in sorted(counts.items()):
        label = _summary_label(key, value)
        summary_parts.append(f"[bold]{value}[/bold] {label}")
    summary_text = " · ".join(summary_parts)

    title = f"[bold]{task_name}[/bold]" if task_name else "Task Results"
    panel = Panel(
        Group(*renderables),
        title=title,
        subtitle=summary_text,
        border_style="cyan",
        padding=(0, 1),
    )
    console.print(panel)

__all__ = ["format_typed_outputs"]
