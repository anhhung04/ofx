"""UI helper functions for consistent command output across OFX."""

from typing import Any
from rich.panel import Panel
from ofx.settings import get_console

console = get_console()


def success_panel(title: str, message: str, details: dict[str, Any] | None = None) -> Panel:
    """Create a success panel with consistent styling.
    
    Args:
        title: Panel title (will be prefixed with [OK])
        message: Main success message
        details: Optional dictionary of key-value pairs to display
    
    Returns:
        Configured Panel object
    """
    content = f"[bold green]{message}[/bold green]"
    
    if details:
        content += "\n"
        for key, value in details.items():
            content += f"\n[bold]{key}:[/bold] {value}"
    
    return Panel(
        content,
        title=f"[bold green][OK] {title}[/bold green]",
        border_style="green"
    )


def error_panel(title: str, message: str, details: str | None = None) -> Panel:
    """Create an error panel with consistent styling.
    
    Args:
        title: Panel title (will be prefixed with [X])
        message: Main error message
        details: Optional additional error details
    
    Returns:
        Configured Panel object
    """
    content = f"[bold red]{message}[/bold red]"
    
    if details:
        content += f"\n[red]{details}[/red]"
    
    return Panel(
        content,
        title=f"[bold red][X] {title}[/bold red]",
        border_style="red"
    )


def warning_panel(title: str, message: str, hint: str | None = None) -> Panel:
    """Create a warning panel with consistent styling.
    
    Args:
        title: Panel title (will be prefixed with [!])
        message: Main warning message
        hint: Optional hint or suggestion
    
    Returns:
        Configured Panel object
    """
    content = f"[bold yellow]{message}[/bold yellow]"
    
    if hint:
        content += f"\n[dim]{hint}[/dim]"
    
    return Panel(
        content,
        title=f"[bold yellow][!] {title}[/bold yellow]",
        border_style="yellow"
    )


def info_panel(title: str, message: str, details: dict[str, Any] | None = None) -> Panel:
    """Create an info panel with consistent styling.
    
    Args:
        title: Panel title (will be prefixed with [?])
        message: Main info message
        details: Optional dictionary of key-value pairs to display
    
    Returns:
        Configured Panel object
    """
    content = message
    
    if details:
        content += "\n"
        for key, value in details.items():
            content += f"\n[bold]{key}:[/bold] {value}"
    
    return Panel(
        content,
        title=f"[?] {title}",
        border_style="cyan"
    )


def print_success(title: str, message: str, details: dict[str, Any] | None = None) -> None:
    """Print a success panel."""
    console.print(success_panel(title, message, details))


def print_error(title: str, message: str, details: str | None = None) -> None:
    """Print an error panel."""
    console.print(error_panel(title, message, details))


def print_warning(title: str, message: str, hint: str | None = None) -> None:
    """Print a warning panel."""
    console.print(warning_panel(title, message, hint))


def print_info(title: str, message: str, details: dict[str, Any] | None = None) -> None:
    """Print an info panel."""
    console.print(info_panel(title, message, details))
