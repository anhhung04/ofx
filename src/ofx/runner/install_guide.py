"""Rich install-guide rendering for missing workflow tools."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ofx.runner.tool_installer import ToolInstallStep


def render_install_guide(
    steps: list[ToolInstallStep],
    *,
    console: Console | None = None,
) -> None:
    """Render a detailed install guide for tools that are missing.

    Shown when auto-install is disabled so the user knows exactly what to
    install and how — grouped by strategy (binary download, shell command,
    manual instructions).
    """
    if not steps:
        return

    con = console or Console()
    table = Table(title="Missing Tools — Install Guide", show_lines=True)
    table.add_column("Tool", style="bold cyan")
    table.add_column("How to install", style="white")
    table.add_column("Details", style="dim")

    for step in steps:
        if step.strategy == "binary":
            how = Markdown(f"Download prebuilt binary:\n```\n{step.command}\n```")
        elif step.strategy == "shell":
            how = Markdown(f"Run install command:\n```bash\n{step.command}\n```")
        else:
            how = Markdown(step.command)
        table.add_row(step.tool, how, step.detail or "—")

    con.print()
    con.print(
        Panel(
            "Auto-install is **disabled**. Install the tools below, then re-run "
            "your workflow.\n\nOr re-run with [bold]--install-tools[/bold] to "
            "install automatically.",
            title="Tools Required",
            border_style="yellow",
        )
    )
    con.print(table)
    con.print()


__all__ = ["render_install_guide"]
