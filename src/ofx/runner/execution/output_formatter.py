"""Format typed task outputs as rich tables for terminal display."""

from __future__ import annotations

from collections import Counter
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Column definitions per output type: (field, header, style, max_width|None)
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

_STATUS_CODE_STYLES = {
    2: "green",
    3: "yellow",
    4: "red",
    5: "bold red",
}


def _cell_value(item: dict[str, Any], field: str) -> str:
    """Extract a display-friendly string from a typed output dict field."""
    val = item.get(field)
    if val is None or val == "" or val == 0:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val[:5]) + ("…" if len(val) > 5 else "")
    if isinstance(val, bool):
        return "✓" if val else ""
    return str(val)


def _cell_style(item: dict[str, Any], field: str, base_style: str) -> str:
    """Return a contextual style for specific field values."""
    if field == "severity":
        return _SEVERITY_STYLES.get(str(item.get(field, "")).lower(), base_style)
    if field == "status_code":
        code = item.get(field, 0)
        if isinstance(code, int) and code > 0:
            return _STATUS_CODE_STYLES.get(code // 100, base_style)
    return base_style


def format_typed_outputs(
    typed_outputs: list[dict[str, Any]],
    task_name: str = "",
    console: Console | None = None,
) -> None:
    """Render typed task outputs as rich tables to the console.

    Groups items by ``_type``, builds a table per type using the column
    definitions above, and prints inside a panel.
    """
    if not typed_outputs:
        return

    console = console or Console()

    # Group by _type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for item in typed_outputs:
        t = item.get("_type", "unknown")
        by_type.setdefault(t, []).append(item)

    renderables = []

    for type_name, items in by_type.items():
        columns = _TYPE_COLUMNS.get(type_name)
        if not columns:
            # Unknown type — show count only
            renderables.append(
                Text(f"  {type_name}: {len(items)} item(s)", style="dim")
            )
            continue

        table = Table(
            show_header=True,
            header_style="bold",
            show_lines=False,
            pad_edge=False,
            expand=False,
        )
        for _, header, style, max_w in columns:
            table.add_column(header, style=style, max_width=max_w, no_wrap=max_w is not None)

        # Skip groups where every item has empty data columns
        data_fields = [f for f, _, _, _ in columns]
        non_empty_items = [
            item
            for item in items
            if any(_cell_value(item, f) for f in data_fields)
        ]
        if not non_empty_items:
            continue

        # Cap rows to avoid flooding the terminal
        items = non_empty_items
        max_rows = 50
        for item in items[:max_rows]:
            cells = []
            for field, _, style, _ in columns:
                val = _cell_value(item, field)
                cell_style = _cell_style(item, field, style)
                cells.append(Text(val, style=cell_style) if cell_style != style else val)
            table.add_row(*cells)

        if len(items) > max_rows:
            table.add_row(*[f"… +{len(items) - max_rows} more" if i == 0 else "" for i in range(len(columns))])

        renderables.append(table)

    if not renderables:
        return

    # Build summary line
    counts = Counter(item.get("_type", "?") for item in typed_outputs)
    summary_parts = []
    for k, v in sorted(counts.items()):
        label = k if v == 1 else (k + "es" if k.endswith("s") else k + "s")
        summary_parts.append(f"[bold]{v}[/bold] {label}")
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
