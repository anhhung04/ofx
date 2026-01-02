"""
Doctor command to check system dependencies, tools, and overall system health.

This module provides a suite of commands to diagnose the local environment, ensuring that
all necessary dependencies are available and correctly configured for OFX to run smoothly.
It checks for essential and recommended tools, Python packages, system resources,
network connectivity, and OFX-specific configurations.
"""

import os
import shutil
import subprocess
from pathlib import Path

import typer

app = typer.Typer()

NAME = "doctor"
HELP = "Diagnose and check system dependencies for OFX."

_console = None


def get_console():
    """
    Returns a lazily-initialized Rich console object with red team theme.
    This prevents the `rich` library from being imported at startup, speeding up
    the CLI's initial response time.
    """
    global _console
    if _console is None:
        from ofx.settings import get_console as get_themed_console
        _console = get_themed_console()
    return _console


# Configuration for essential command-line tools
ESSENTIAL_TOOLS = {
    "git": {
        "check": "git --version",
        "description": "Version control system, for managing project and workflow repositories.",
        "install_cmd": "sudo apt update && sudo apt install -y git",
        "install_cmd_fallback": "sudo dnf install -y git",
    },
    "python3": {
        "check": "python3 --version",
        "min_version": "3.10",
        "description": "The Python runtime environment for executing OFX.",
        "install_cmd": "sudo apt update && sudo apt install -y python3 python3-pip",
        "install_cmd_fallback": "sudo dnf install -y python3 python3-pip",
    },
}

# Configuration for recommended (but not essential) command-line tools
RECOMMENDED_TOOLS = {
    "uv": {
        "check": "uv --version",
        "description": "A fast Python package installer that can speed up dependency management.",
        "install_cmd": "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "install_cmd_fallback": "pip install uv",
    },
    "docker": {
        "check": "docker --version",
        "description": "Container runtime, useful for isolated execution environments.",
        "install_cmd": "curl https://get.docker.com | sh",
        "install_cmd_fallback": "sudo dnf install -y docker",
    },
    "go": {
        "check": "go version",
        "description": "Go programming language, useful for building efficient tools and services.",
        "install_cmd": "sudo apt update && sudo apt install -y golang-go",
        "install_cmd_fallback": "sudo dnf install -y golang",
    },
    "node": {
        "check": "node --version",
        "description": "Node.js runtime, essential for JavaScript/TypeScript development.",
        "install_cmd": "sudo apt update && sudo apt install -y nodejs npm",
        "install_cmd_fallback": "sudo dnf install -y nodejs npm",
    },
}


def get_linux_distro() -> str:
    """
    Detect the Linux distribution to determine the appropriate package manager.
    """
    try:
        # Check /etc/os-release first (systemd standard)
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    distro_id = line.split("=")[1].strip().strip('"')
                    if distro_id in ["ubuntu", "debian", "linuxmint", "pop"]:
                        return "debian"
                    elif distro_id in ["fedora", "centos", "rhel", "almalinux", "rocky"]:
                        return "redhat"
                    elif distro_id in ["arch", "manjaro", "endeavouros"]:
                        return "arch"
                    elif distro_id in ["opensuse", "sles"]:
                        return "suse"
    except FileNotFoundError:
        pass

    # Fallback to checking for package managers
    if shutil.which("apt"):
        return "debian"
    elif shutil.which("dnf"):
        return "redhat"
    elif shutil.which("pacman"):
        return "arch"
    elif shutil.which("zypper"):
        return "suse"

    return "unknown"


def check_tool(
    tool_name: str, config: dict
) -> tuple[bool, str | None, str | None]:
    """
    Checks if a given tool is installed and returns its version.
    """
    if not shutil.which(tool_name):
        return False, None, f"'{tool_name}' not found in system PATH."

    check_cmd = config.get("check")
    if not check_cmd:
        return True, "Installed (version check not configured)", None

    try:
        result = subprocess.run(
            check_cmd.split(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return True, result.stdout.strip().split("\n")[0], None
        else:
            return True, None, f"Failed to get version: {result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        return True, None, f"Error checking version: {e}"


def check_network_connectivity(console) -> tuple[bool, str]:
    """
    Performs a network connectivity test.
    """
    try:
        import httpx
    except ImportError:
        return False, "The 'httpx' library is required. Please install it."

    test_urls = { "Google DNS": "https://8.8.8.8", "GitHub": "https://github.com" }
    for name, url in test_urls.items():
        try:
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
            return True, f"Successfully connected to {name}."
        except (httpx.RequestError, httpx.HTTPStatusError):
            continue

    return False, "Could not connect to any test network endpoints."

def dns_resolution_check(console) -> tuple[bool, str]:
    """
    Checks DNS resolution for common domains.
    """
    import socket
    domains = ["google.com", "github.com"]
    for domain in domains:
        try:
            socket.gethostbyname(domain)
        except (socket.gaierror, Exception) as e:
            return False, f"Failed to resolve {domain}: {e}"
    return True, "DNS resolution is working correctly."

def check_system_resources() -> dict[str, tuple[bool, str, dict]]:
    """
    Checks critical system resources like disk space and memory.
    """
    results = {}

    try:
        _, _, free = shutil.disk_usage(Path.home())
        free_gb = free / (1024**3)
        results["disk"] = (free_gb > 2, f"{free_gb:.1f}GB free on home partition.", {})
    except Exception as e:
        results["disk"] = (False, f"Could not check disk space: {e}", {})

    try:
        import psutil
        mem = psutil.virtual_memory()
        results["memory"] = (mem.percent < 90, f"{mem.percent}% used.", {})
    except ImportError:
        results["memory"] = (True, "Skipping memory check: 'psutil' not installed.", {})
    except Exception as e:
        results["memory"] = (False, f"Could not check memory: {e}", {})

    return results

def check_ofx_directories() -> dict[str, tuple[bool, str]]:
    """
    Verifies that OFX's data directories exist and have the correct permissions.
    """
    try:
        from ofx.settings import BASE_DATA_DIR
    except ImportError:
        return {"configuration": (False, "OFX settings could not be imported.")}

    directories = { "Data": BASE_DATA_DIR, "Workflows": BASE_DATA_DIR / "workflows" }
    results = {}
    for name, path in directories.items():
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                results[name] = (True, f"Created at {path}")
            except Exception as e:
                results[name] = (False, f"Cannot create directory: {e}")
        else:
            results[name] = (os.access(path, os.R_OK | os.W_OK), f"Exists at {path}")
    return results

@app.command(name="check")
def run_all_checks(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information.")
):
    """
    Run a comprehensive check of all system dependencies and configurations for OFX.
    """
    console = get_console()
    from rich.panel import Panel
    from rich.table import Table

    all_ok = True

    sections = {"Tools": ESSENTIAL_TOOLS}
    if verbose:
        sections["Optional Tools"] = RECOMMENDED_TOOLS

    for title, tools in sections.items():
        table = Table(title=title, expand=True, border_style="cyan")
        table.add_column("Tool", style="cyan", no_wrap=True)
        table.add_column("Status", style="green", justify="center")
        table.add_column("Details", style="yellow", no_wrap=True)
        for tool, config in tools.items():
            installed, version, error_msg = check_tool(tool, config)
            if installed:
                details = version or "OK"
                table.add_row(f"[bold]{tool}[/bold]", "[green]✅[/green]", f"[dim]{details}[/dim]")
            else:
                all_ok = False
                details = error_msg or "Not found"
                table.add_row(f"[bold]{tool}[/bold]", "[red]❌[/red]", f"[red]{details}[/red]")
        console.print(table)

    system_table = Table(title="System Health", expand=True, border_style="cyan")
    system_table.add_column("Check", style="cyan", no_wrap=True)
    system_table.add_column("Status", style="green", justify="center")
    system_table.add_column("Details", style="yellow", no_wrap=True)

    net_ok, net_msg = check_network_connectivity(console)
    status = "[green]✅[/green]" if net_ok else "[red]❌[/red]"
    details = "[dim]Connected[/dim]" if net_ok else f"[red]{net_msg}[/red]"
    system_table.add_row("Network", status, details)
    if not net_ok:
        all_ok = False

    for res, (ok, msg, _) in check_system_resources().items():
        status = "[green]✅[/green]" if ok else "[yellow]⚠️[/yellow]"
        details = f"[dim]{msg}[/dim]" if ok else f"[yellow]{msg}[/yellow]"
        system_table.add_row(f"{res.title()}", status, details)

    for name, (ok, msg) in check_ofx_directories().items():
        status = "[green]✅[/green]" if ok else "[red]❌[/red]"
        details = f"[dim]{msg}[/dim]" if ok else f"[red]{msg}[/red]"
        system_table.add_row(f"OFX {name}", status, details)
        if not ok:
            all_ok = False

    console.print(system_table)

    if all_ok:
        console.print(Panel("[bold green]✅ All checks passed[/bold green]", title="Report"))
    else:
        console.print(Panel("[bold red]❌ Some checks failed[/bold red]", title="Report"))
        raise typer.Exit(code=1)

@app.command()
def install_help(
    tool: str | None = typer.Argument(None, help="Show help for a specific tool.")
):
    """
    Provide installation instructions for required tools.
    """
    console = get_console()
    from rich.panel import Panel

    distro = get_linux_distro()
    all_tools = {**ESSENTIAL_TOOLS, **RECOMMENDED_TOOLS}

    if tool and tool in all_tools:
        tool_config = all_tools[tool]
        install_cmd = tool_config.get("install_cmd")
        fallback_cmd = tool_config.get("install_cmd_fallback")

        if distro == "debian" and install_cmd:
            display_cmd = install_cmd
        elif distro in ["redhat", "arch", "suse"] and fallback_cmd:
            display_cmd = fallback_cmd
        else:
            display_cmd = install_cmd or fallback_cmd or "Installation command not available for this distribution"

        console.print(Panel(
            f"[bold]Description:[/bold] {tool_config['description']}\n\n[bold]Install command:[/bold]\n\"{display_cmd}\"",
            title=f"Install: {tool}"
        ))
    else:
        console.print(f"[bold cyan]Detected Linux distribution: {distro}[/bold cyan]\n")
        console.print("[bold cyan]Available tools:[/bold cyan]")

        for name, conf in all_tools.items():
            install_cmd = conf.get("install_cmd")
            fallback_cmd = conf.get("install_cmd_fallback")

            if distro == "debian" and install_cmd:
                display_cmd = install_cmd.split(" && ")[-1]  # Show just the install part
            elif distro in ["redhat", "arch", "suse"] and fallback_cmd:
                display_cmd = fallback_cmd
            else:
                display_cmd = install_cmd or fallback_cmd or "N/A"

            console.print(f"  [cyan]{name}:[/cyan] \"{display_cmd}\"")
