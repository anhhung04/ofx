"""Doctor command to check system dependencies and tools."""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()
console = Console()

NAME = "doctor"
HELP = "Check system dependencies and required tools."

# Essential tools required for OFX
ESSENTIAL_TOOLS = {
    "git": {
        "check": "git --version",
        "min_version": None,
        "description": "Version control system",
        "install_help": "https://git-scm.com/downloads",
    },
    "curl": {
        "check": "curl --version",
        "min_version": None,
        "description": "HTTP client for downloading files",
        "install_help": "Usually pre-installed. Use package manager: apt/yum/brew install curl",
    },
    "python3": {
        "check": "python3 --version",
        "min_version": "3.10",
        "description": "Python runtime",
        "install_help": "https://www.python.org/downloads/",
    },
}

# Optional but recommended tools
RECOMMENDED_TOOLS = {
    "uv": {
        "check": "uv --version",
        "min_version": None,
        "description": "Fast Python package installer",
        "install_help": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    },
    "go": {
        "check": "go version",
        "min_version": None,
        "description": "Go programming language",
        "install_help": "https://go.dev/doc/install",
    },
    "docker": {
        "check": "docker --version",
        "min_version": None,
        "description": "Container runtime",
        "install_help": "https://docs.docker.com/get-docker/",
    },
    "node": {
        "check": "node --version",
        "min_version": None,
        "description": "Node.js runtime",
        "install_help": "https://nodejs.org/en/download/",
    },
}


def check_tool(
    tool_name: str, config: Dict
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if a tool is installed and get its version.

    Args:
        tool_name: Name of the tool to check
        config: Tool configuration dict with check command

    Returns:
        Tuple of (is_installed, version, error_message)
    """
    # First check if binary exists in PATH
    if not shutil.which(tool_name):
        return False, None, f"{tool_name} not found in PATH"

    # Try to get version
    check_cmd = config.get("check")
    if check_cmd:
        try:
            result = subprocess.run(
                check_cmd.split(),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                return True, version, None
            else:
                return True, None, f"Failed to get version: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return True, None, "Version check timed out"
        except Exception as e:
            return True, None, f"Error checking version: {e}"

    return True, None, None


def check_path_directories() -> List[str]:
    """Get list of directories in PATH."""
    import os

    return os.environ.get("PATH", "").split(":")


def check_python_packages() -> Dict[str, bool]:
    """Check if essential Python packages are installed."""
    packages = ["pydantic", "typer", "rich", "httpx", "yaml"]
    installed = {}

    for package in packages:
        try:
            __import__(package)
            installed[package] = True
        except ImportError:
            installed[package] = False

    return installed


@app.command()
def check(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
    check_recommended: bool = typer.Option(
        True, "--recommended/--essential", help="Check recommended tools"
    ),
):
    """
    Check system dependencies and required tools.

    This command verifies that all necessary tools are installed and accessible.
    """
    console.print("\n[bold cyan]🔍 OFX System Doctor[/bold cyan]\n")

    # Check essential tools
    console.print("[bold]Essential Tools:[/bold]")
    essential_table = Table(show_header=True, header_style="bold magenta")
    essential_table.add_column("Tool", style="cyan", width=12)
    essential_table.add_column("Status", width=10)
    essential_table.add_column("Version", width=30)
    essential_table.add_column("Description", width=35)

    all_essential_ok = True
    for tool_name, config in ESSENTIAL_TOOLS.items():
        is_installed, version, error = check_tool(tool_name, config)

        if is_installed:
            status = "[green]✓ Installed[/green]"
            version_str = version or "Unknown"
        else:
            status = "[red]✗ Missing[/red]"
            version_str = error or "Not found"
            all_essential_ok = False

        essential_table.add_row(
            tool_name,
            status,
            version_str,
            config["description"],
        )

    console.print(essential_table)

    # Check recommended tools if requested
    if check_recommended:
        console.print("\n[bold]Recommended Tools:[/bold]")
        recommended_table = Table(show_header=True, header_style="bold magenta")
        recommended_table.add_column("Tool", style="cyan", width=12)
        recommended_table.add_column("Status", width=10)
        recommended_table.add_column("Version", width=30)
        recommended_table.add_column("Description", width=35)

        for tool_name, config in RECOMMENDED_TOOLS.items():
            is_installed, version, error = check_tool(tool_name, config)

            if is_installed:
                status = "[green]✓ Installed[/green]"
                version_str = version or "Unknown"
            else:
                status = "[yellow]○ Optional[/yellow]"
                version_str = "Not installed"

            recommended_table.add_row(
                tool_name,
                status,
                version_str,
                config["description"],
            )

        console.print(recommended_table)

    # Check Python packages
    console.print("\n[bold]Python Dependencies:[/bold]")
    packages = check_python_packages()
    pkg_table = Table(show_header=True, header_style="bold magenta")
    pkg_table.add_column("Package", style="cyan", width=15)
    pkg_table.add_column("Status", width=15)

    all_packages_ok = True
    for pkg_name, is_installed in packages.items():
        if is_installed:
            pkg_table.add_row(pkg_name, "[green]✓ Installed[/green]")
        else:
            pkg_table.add_row(pkg_name, "[red]✗ Missing[/red]")
            all_packages_ok = False

    console.print(pkg_table)

    # Show verbose information
    if verbose:
        console.print("\n[bold]System Information:[/bold]")
        info_table = Table(show_header=False)
        info_table.add_column("Property", style="cyan", width=20)
        info_table.add_column("Value", width=70)

        import platform
        import sys

        info_table.add_row("Python Version", sys.version.split()[0])
        info_table.add_row("Python Executable", sys.executable)
        info_table.add_row("Platform", platform.platform())
        info_table.add_row("Architecture", platform.machine())

        path_dirs = check_path_directories()
        info_table.add_row("PATH Directories", f"{len(path_dirs)} directories")

        console.print(info_table)

        if len(path_dirs) > 0:
            console.print("\n[bold]PATH Directories:[/bold]")
            for i, path_dir in enumerate(path_dirs[:10], 1):
                console.print(f"  {i}. {path_dir}")
            if len(path_dirs) > 10:
                console.print(f"  ... and {len(path_dirs) - 10} more")

    # Summary
    console.print()
    if all_essential_ok and all_packages_ok:
        console.print(
            Panel(
                "[green]✓ All essential dependencies are installed![/green]\n"
                "Your system is ready to run OFX workflows.",
                title="[bold green]Status: Ready[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                "[red]✗ Some essential dependencies are missing.[/red]\n"
                "Please install the missing tools to ensure OFX works correctly.\n\n"
                "Run [cyan]ofx doctor install-help[/cyan] for installation instructions.",
                title="[bold red]Status: Issues Found[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command()
def install_help(
    tool: Optional[str] = typer.Argument(
        None, help="Specific tool to show installation help for"
    ),
):
    """
    Show installation instructions for tools.

    Args:
        tool: Optional specific tool name to show help for
    """
    console.print("\n[bold cyan]📦 Tool Installation Help[/bold cyan]\n")

    all_tools = {**ESSENTIAL_TOOLS, **RECOMMENDED_TOOLS}

    if tool:
        if tool not in all_tools:
            console.print(f"[red]Error:[/red] Unknown tool '{tool}'")
            console.print(f"Available tools: {', '.join(all_tools.keys())}")
            raise typer.Exit(code=1)

        config = all_tools[tool]
        console.print(
            Panel(
                f"[bold]{tool}[/bold]\n\n"
                f"{config['description']}\n\n"
                f"[cyan]Installation:[/cyan]\n{config['install_help']}",
                title=f"[bold cyan]{tool.upper()}[/bold cyan]",
                border_style="cyan",
            )
        )
    else:
        # Show all essential tools
        console.print("[bold]Essential Tools:[/bold]\n")
        for tool_name, config in ESSENTIAL_TOOLS.items():
            console.print(f"[cyan]• {tool_name}[/cyan]: {config['description']}")
            console.print(f"  {config['install_help']}\n")

        console.print("\n[bold]Recommended Tools:[/bold]\n")
        for tool_name, config in RECOMMENDED_TOOLS.items():
            console.print(f"[cyan]• {tool_name}[/cyan]: {config['description']}")
            console.print(f"  {config['install_help']}\n")


@app.command()
def path(
    show_all: bool = typer.Option(
        False, "--all", "-a", help="Show all PATH directories"
    ),
):
    """Show PATH environment variable directories."""
    console.print("\n[bold cyan]📂 PATH Directories[/bold cyan]\n")

    path_dirs = check_path_directories()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=5)
    table.add_column("Directory", width=70)
    table.add_column("Exists", width=10)

    limit = None if show_all else 20
    for i, path_dir in enumerate(path_dirs[:limit], 1):
        exists = Path(path_dir).exists()
        exists_str = "[green]✓[/green]" if exists else "[red]✗[/red]"
        table.add_row(str(i), path_dir, exists_str)

    if not show_all and len(path_dirs) > 20:
        table.add_row("...", f"and {len(path_dirs) - 20} more", "")

    console.print(table)
    console.print(f"\n[bold]Total:[/bold] {len(path_dirs)} directories")
