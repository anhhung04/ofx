"""Doctor command to check system dependencies and tools."""

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from ofx.settings import BASE_DATA_DIR, settings
    HAS_OFX_CONFIG = True
except ImportError:
    HAS_OFX_CONFIG = False
    BASE_DATA_DIR = Path.home() / ".local" / "share" / "ofx"

app = typer.Typer()
console = Console()

NAME = "doctor"
HELP = "Check system dependencies and required tools."

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
    """Check if a tool is installed and get its version"""
    if not shutil.which(tool_name):
        return False, None, f"{tool_name} not found in PATH"

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
    packages = ["pydantic", "typer", "rich", "httpx", "yaml", "cryptography", "boto3"]
    installed = {}

    for package in packages:
        try:
            __import__(package)
            installed[package] = True
        except ImportError:
            installed[package] = False

    return installed


def check_network_connectivity() -> Tuple[bool, str]:
    """Check basic network connectivity."""
    if not HAS_HTTPX:
        return False, "httpx not available for network checks"

    try:
        import httpx
        # Test connectivity to common endpoints
        test_urls = [
            "https://httpbin.org/status/200",
            "https://github.com",
            "https://pypi.org"
        ]

        for url in test_urls:
            try:
                response = httpx.get(url, timeout=5.0)
                if response.status_code == 200:
                    return True, f"Connected (tested {url})"
            except Exception:
                continue

        return False, "No connectivity to test endpoints"
    except Exception as e:
        return False, f"Network check failed: {e}"


def check_disk_space(path: Optional[Path] = None) -> Tuple[bool, str, Dict[str, float]]:
    """Check available disk space with detailed metrics."""
    if path is None:
        path = Path.home()

    try:
        stat = os.statvfs(path)
        # Get space in bytes first
        total_bytes = stat.f_blocks * stat.f_frsize
        free_bytes = stat.f_bavail * stat.f_frsize
        used_bytes = total_bytes - free_bytes

        # Convert to GB
        total_gb = total_bytes / (1024**3)
        free_gb = free_bytes / (1024**3)
        used_gb = used_bytes / (1024**3)
        used_percent = (used_bytes / total_bytes) * 100

        metrics = {
            "total_gb": total_gb,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "used_percent": used_percent,
        }

        if free_gb < 1.0:  # Less than 1GB free
            return False, f"{free_gb:.1f}GB free", metrics
        elif free_gb < 5.0:  # Less than 5GB free
            return True, f"{free_gb:.1f}GB free", metrics
        else:
            return True, f"{free_gb:.1f}GB free", metrics
    except Exception as e:
        return False, f"Unable to check disk space: {e}", {}


def check_memory() -> Tuple[bool, str, Dict[str, float]]:
    """Check system memory with detailed metrics."""
    if not HAS_PSUTIL:
        return True, "psutil not available (install for detailed memory info)", {}

    try:
        import psutil
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        used_gb = mem.used / (1024**3)
        percent_used = mem.percent

        swap_total_gb = swap.total / (1024**3)
        swap_used_gb = swap.used / (1024**3)
        swap_percent = swap.percent

        metrics = {
            "total_gb": total_gb,
            "available_gb": available_gb,
            "used_gb": used_gb,
            "percent_used": percent_used,
            "swap_total_gb": swap_total_gb,
            "swap_used_gb": swap_used_gb,
            "swap_percent": swap_percent,
        }

        if percent_used > 95:
            return False, f"{available_gb:.1f}GB available", metrics
        elif percent_used > 80:
            return True, f"{available_gb:.1f}GB available", metrics
        else:
            return True, f"{available_gb:.1f}GB available", metrics
    except Exception as e:
        return False, f"Memory check failed: {e}", {}


def check_file_permissions(path: Path) -> Tuple[bool, str]:
    """Check file/directory permissions."""
    if not path.exists():
        return False, "Path does not exist"

    try:
        # Check if readable
        if not os.access(path, os.R_OK):
            return False, "Not readable"

        # Check if writable (for directories)
        if path.is_dir() and not os.access(path, os.W_OK):
            return False, "Directory not writable"

        # Check if executable (for directories)
        if path.is_dir() and not os.access(path, os.X_OK):
            return False, "Directory not executable"

        return True, "OK"
    except Exception as e:
        return False, f"Permission check failed: {e}"


def check_ofx_directories() -> Dict[str, Tuple[bool, str]]:
    """Check OFX-specific directories and permissions."""
    directories = {
        "data_dir": BASE_DATA_DIR,
        "workflows_dir": BASE_DATA_DIR / "workflows",
        "logs_dir": BASE_DATA_DIR / "logs",
        "cache_dir": BASE_DATA_DIR / "cache",
    }

    results = {}
    for name, path in directories.items():
        if path.exists():
            ok, msg = check_file_permissions(path)
            results[name] = (ok, msg)
        else:
            # Try to create it
            try:
                path.mkdir(parents=True, exist_ok=True)
                results[name] = (True, "Created")
            except Exception as e:
                results[name] = (False, f"Cannot create: {e}")

    return results


def benchmark_disk_io(test_file: Optional[Path] = None) -> Tuple[float, float]:
    """Benchmark disk I/O performance."""
    if test_file is None:
        test_file = BASE_DATA_DIR / ".doctor_test"

    try:
        # Write test
        data = b"0" * (1024 * 1024)  # 1MB
        start_time = time.time()
        with open(test_file, "wb") as f:
            for _ in range(10):  # 10MB total
                f.write(data)
        write_time = time.time() - start_time

        # Read test
        start_time = time.time()
        with open(test_file, "rb") as f:
            while f.read(1024 * 1024):
                pass
        read_time = time.time() - start_time

        # Cleanup
        test_file.unlink(missing_ok=True)

        write_speed = 10 / write_time  # MB/s
        read_speed = 10 / read_time    # MB/s

        return write_speed, read_speed
    except Exception:
        return 0.0, 0.0


def check_security_settings() -> List[str]:
    """Check basic security settings."""
    issues = []

    # Check if running as root (generally not recommended for OFX)
    if os.geteuid() == 0:
        issues.append("Running as root - consider using a regular user account")

    # Check file permissions on sensitive directories
    home = Path.home()
    ssh_dir = home / ".ssh"
    if ssh_dir.exists():
        if oct(ssh_dir.stat().st_mode)[-3:] != "700":
            issues.append("SSH directory permissions should be 700")

    # Check if core dumps are enabled (could leak sensitive data)
    try:
        with open("/proc/sys/kernel/core_pattern", "r") as f:
            core_pattern = f.read().strip()
            if core_pattern != "/dev/null":
                issues.append("Core dumps enabled - consider disabling for security")
    except FileNotFoundError:
        pass  # Not on Linux

    return issues


def validate_config_files() -> Dict[str, Tuple[bool, str]]:
    """Validate OFX configuration files."""
    config_checks = {}

    if not HAS_OFX_CONFIG:
        config_checks["ofx_config"] = (False, "OFX settings not available")
        return config_checks

    try:
        from ofx.settings import settings

        # Check if .env file exists
        env_file = Path(".env")
        if env_file.exists():
            config_checks["env_file"] = (True, f"Found at {env_file.absolute()}")
        else:
            config_checks["env_file"] = (True, "Not found (using defaults)")

        # Check if secrets directory exists and is accessible
        from ofx.settings import SECRETS_DIR
        if SECRETS_DIR.exists():
            ok, msg = check_file_permissions(SECRETS_DIR)
            config_checks["secrets_dir"] = (ok, msg)
        else:
            config_checks["secrets_dir"] = (False, f"Missing: {SECRETS_DIR}")

        # Try to load settings
        try:
            # This will validate the config
            _ = settings.app_name
            config_checks["config_valid"] = (True, "Configuration is valid")
        except Exception as e:
            config_checks["config_valid"] = (False, f"Invalid config: {e}")

    except Exception as e:
        config_checks["ofx_config"] = (False, f"Config check failed: {e}")

    return config_checks


@app.command()
def check(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information"
    ),
    check_recommended: bool = typer.Option(
        True, "--recommended/--essential", help="Check recommended tools"
    ),
    include_network: bool = typer.Option(
        True, "--network/--no-network", help="Include network connectivity checks"
    ),
    include_performance: bool = typer.Option(
        False, "--performance", help="Include performance benchmarks"
    ),
    include_security: bool = typer.Option(
        False, "--security", help="Include security checks"
    ),
):
    """Check system dependencies and required tools"""
    console.print("\n[bold cyan]System Doctor[/bold cyan]\n")

    all_essential_ok = True
    all_packages_ok = True

    # Essential Tools Check
    console.print("[bold]Essential Tools:[/bold]")
    essential_table = Table(show_header=True, header_style="bold magenta")
    essential_table.add_column("Tool", style="cyan", width=12)
    essential_table.add_column("Status", width=10)
    essential_table.add_column("Version", width=30)
    essential_table.add_column("Description", width=35)

    for tool_name, config in ESSENTIAL_TOOLS.items():
        is_installed, version, error = check_tool(tool_name, config)

        if is_installed:
            status = "[green][OK] Installed[/green]"
            version_str = version or "Unknown"
        else:
            status = "[red][FAIL] Missing[/red]"
            version_str = error or "Not found"
            all_essential_ok = False

        essential_table.add_row(
            tool_name,
            status,
            version_str,
            config["description"],
        )

    console.print(essential_table)

    # Recommended Tools Check
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
                status = "[green][OK] Installed[/green]"
                version_str = version or "Unknown"
            else:
                status = "[yellow][SKIP] Optional[/yellow]"
                version_str = "Not installed"

            recommended_table.add_row(
                tool_name,
                status,
                version_str,
                config["description"],
            )

        console.print(recommended_table)

    # Python Dependencies Check
    console.print("\n[bold]Python Dependencies:[/bold]")
    packages = check_python_packages()
    pkg_table = Table(show_header=True, header_style="bold magenta")
    pkg_table.add_column("Package", style="cyan", width=15)
    pkg_table.add_column("Status", width=15)

    for pkg_name, is_installed in packages.items():
        if is_installed:
            pkg_table.add_row(pkg_name, "[green][OK] Installed[/green]")
        else:
            pkg_table.add_row(pkg_name, "[red][FAIL] Missing[/red]")
            all_packages_ok = False

    console.print(pkg_table)

    # System Resources Check
    console.print("\n[bold]System Resources:[/bold]")
    resources_table = Table(show_header=True, header_style="bold magenta")
    resources_table.add_column("Resource", style="cyan", width=15)
    resources_table.add_column("Status", width=10)
    resources_table.add_column("Details", width=40)

    # Disk space
    disk_ok, disk_msg, disk_metrics = check_disk_space()
    disk_status = "[green][OK] OK[/green]" if disk_ok else "[red][FAIL] Low[/red]"
    resources_table.add_row("Disk Space", disk_status, disk_msg)

    # Memory
    mem_ok, mem_msg, mem_metrics = check_memory()
    mem_status = "[green][OK] OK[/green]" if mem_ok else "[red][FAIL] Low[/red]"
    resources_table.add_row("Memory", mem_status, mem_msg)

    console.print(resources_table)

    # Network Connectivity Check
    if include_network:
        console.print("\n[bold]Network Connectivity:[/bold]")
        net_ok, net_msg = check_network_connectivity()
        net_status = "[green][OK] Connected[/green]" if net_ok else "[red][FAIL] Disconnected[/red]"
        console.print(f"{net_status}: {net_msg}")

    # OFX Directories Check
    console.print("\n[bold]OFX Directories:[/bold]")
    dirs_table = Table(show_header=True, header_style="bold magenta")
    dirs_table.add_column("Directory", style="cyan", width=15)
    dirs_table.add_column("Status", width=10)
    dirs_table.add_column("Details", width=40)

    ofx_dirs = check_ofx_directories()
    for dir_name, (ok, msg) in ofx_dirs.items():
        status = "[green][OK] OK[/green]" if ok else "[red][FAIL] Issue[/red]"
        dirs_table.add_row(dir_name.replace("_dir", ""), status, msg)

    console.print(dirs_table)

    # Configuration Check
    console.print("\n[bold]Configuration:[/bold]")
    config_table = Table(show_header=True, header_style="bold magenta")
    config_table.add_column("Config Item", style="cyan", width=15)
    config_table.add_column("Status", width=10)
    config_table.add_column("Details", width=40)

    config_checks = validate_config_files()
    for check_name, (ok, msg) in config_checks.items():
        status = "[green][OK] OK[/green]" if ok else "[red][FAIL] Issue[/red]"
        config_table.add_row(check_name.replace("_", " ").title(), status, msg)

    console.print(config_table)

    # Performance Benchmarks
    if include_performance:
        console.print("\n[bold]Performance Benchmarks:[/bold]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running disk I/O benchmark...", total=None)
            write_speed, read_speed = benchmark_disk_io()
            progress.update(task, completed=True)

        perf_table = Table(show_header=True, header_style="bold magenta")
        perf_table.add_column("Benchmark", style="cyan", width=15)
        perf_table.add_column("Result", width=20)

        if write_speed > 0:
            perf_table.add_row("Disk Write Speed", f"{write_speed:.1f} MB/s")
            perf_table.add_row("Disk Read Speed", f"{read_speed:.1f} MB/s")
        else:
            perf_table.add_row("Disk I/O", "[red]Benchmark failed[/red]")

        console.print(perf_table)

    # Security Checks
    if include_security:
        console.print("\n[bold]Security Checks:[/bold]")
        security_issues = check_security_settings()

        if security_issues:
            for issue in security_issues:
                console.print(f"[red][WARN] {issue}[/red]")
        else:
            console.print("[green][OK] No security issues detected[/green]")

    # Verbose System Information
    if verbose:
        console.print("\n[bold]System Information:[/bold]")
        info_table = Table(show_header=False)
        info_table.add_column("Property", style="cyan", width=20)
        info_table.add_column("Value", width=70)

        info_table.add_row("Python Version", sys.version.split()[0])
        info_table.add_row("Python Executable", sys.executable)
        info_table.add_row("Platform", platform.platform())
        info_table.add_row("Architecture", platform.machine())

        path_dirs = check_path_directories()
        info_table.add_row("PATH Directories", f"{len(path_dirs)} directories")

        if HAS_PSUTIL:
            import psutil
            cpu_count = psutil.cpu_count()
            info_table.add_row("CPU Cores", str(cpu_count))

        console.print(info_table)

        if len(path_dirs) > 0:
            console.print("\n[bold]PATH Directories:[/bold]")
            for i, path_dir in enumerate(path_dirs[:10], 1):
                console.print(f"  {i}. {path_dir}")
            if len(path_dirs) > 10:
                console.print(f"  ... and {len(path_dirs) - 10} more")

    # Final Status
    console.print()
    overall_ok = all_essential_ok and all_packages_ok

    if overall_ok:
        console.print(
            Panel(
                "[green][OK] All essential dependencies are installed![/green]\n"
                "Your system is ready to run OFX workflows.",
                title="[bold green]Status: Ready[/bold green]",
                border_style="green",
            )
        )
    else:
        issues = []
        if not all_essential_ok:
            issues.append("essential tools")
        if not all_packages_ok:
            issues.append("Python packages")

        console.print(
            Panel(
                f"[red]✗ Some essential dependencies are missing: {', '.join(issues)}.[/red]\n"
                "Please install the missing tools to ensure OFX works correctly.\n\n"
                "Run [cyan]ofx doctor install-help[/cyan] for installation instructions.",
                title="[bold red]Status: Issues Found[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command()
def network(
    timeout: float = typer.Option(5.0, help="Timeout for network tests in seconds"),
):
    """Check network connectivity and DNS resolution"""
    console.print("\n[bold cyan]🌐 Network Connectivity Check[/bold cyan]\n")

    if not HAS_HTTPX:
        console.print("[red]httpx not available. Install with: uv add httpx[/red]")
        raise typer.Exit(1)

    import httpx

    test_urls = [
        ("GitHub", "https://github.com"),
        ("PyPI", "https://pypi.org"),
        ("HTTPBin", "https://httpbin.org/status/200"),
        ("Cloudflare", "https://1.1.1.1"),
    ]

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Service", style="cyan", width=15)
    table.add_column("Status", width=12)
    table.add_column("Response Time", width=15)
    table.add_column("Details", width=30)

    all_ok = True

    for name, url in test_urls:
        try:
            start_time = time.time()
            response = httpx.get(url, timeout=timeout)
            response_time = time.time() - start_time

            if response.status_code == 200:
                status = "[green]✓ OK[/green]"
                details = f"Status {response.status_code}"
            else:
                status = "[yellow]⚠️ Warning[/yellow]"
                details = f"Status {response.status_code}"
                all_ok = False

            table.add_row(name, status, ".2f", details)

        except httpx.TimeoutException:
            table.add_row(name, "[red][FAIL] Timeout[/red]", "N/A", f"Timeout after {timeout}s")
            all_ok = False
        except Exception as e:
            table.add_row(name, "[red][FAIL] Failed[/red]", "N/A", str(e)[:25])
            all_ok = False

    console.print(table)

    # DNS Resolution Test
    console.print("\n[bold]DNS Resolution:[/bold]")
    dns_tests = ["github.com", "pypi.org", "httpbin.org"]

    for domain in dns_tests:
        try:
            import socket
            ip = socket.gethostbyname(domain)
            console.print(f"[green][OK] {domain}[/green] → {ip}")
        except Exception as e:
            console.print(f"[red][FAIL] {domain}[/red] → Failed: {e}")
            all_ok = False

    console.print()
    if all_ok:
        console.print("[green][OK] Network connectivity is good![/green]")
    else:
        console.print("[red][FAIL] Network issues detected[/red]")


@app.command()
def performance(
    disk_test: bool = typer.Option(True, help="Run disk I/O benchmark"),
    cpu_test: bool = typer.Option(True, help="Run CPU benchmark"),
):
    """Run performance benchmarks"""
    console.print("\n[bold cyan]⚡ Performance Benchmarks[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Benchmark", style="cyan", width=20)
    table.add_column("Result", width=25)
    table.add_column("Status", width=15)

    # Disk I/O Benchmark
    if disk_test:
        console.print("Running disk I/O benchmark...")
        write_speed, read_speed = benchmark_disk_io()

        if write_speed > 0:
            table.add_row(
                "Disk Write Speed",
                f"{write_speed:.1f} MB/s",
                "[green][OK] Good[/green]" if write_speed > 50 else "[yellow][WARN] Slow[/yellow]"
            )
            table.add_row(
                "Disk Read Speed",
                f"{read_speed:.1f} MB/s",
                "[green][OK] Good[/green]" if read_speed > 100 else "[yellow][WARN] Slow[/yellow]"
            )
        else:
            table.add_row("Disk I/O", "Failed", "[red][FAIL] Error[/red]")

    # CPU Benchmark
    if cpu_test:
        console.print("Running CPU benchmark...")
        try:
            # Simple CPU benchmark - calculate pi digits
            import math

            start_time = time.time()
            # Calculate some math operations
            result = 0
            for i in range(100000):
                result += math.sin(i) * math.cos(i)
            cpu_time = time.time() - start_time

            # Rough performance metric
            perf_score = 100000 / cpu_time  # operations per second

            status = "[green][OK] Good[/green]" if perf_score > 50000 else "[yellow][WARN] Slow[/yellow]"
            table.add_row("CPU Performance", f"{perf_score:.0f} ops/sec", status)

        except Exception as e:
            table.add_row("CPU Performance", f"Error: {e}", "[red][FAIL] Failed[/red]")

    # Memory Benchmark
    if HAS_PSUTIL:
        try:
            import psutil
            mem = psutil.virtual_memory()
            mem_test = []

            # Memory allocation test
            start_time = time.time()
            data = [0] * (1024 * 1024)  # 1M integers
            alloc_time = time.time() - start_time

            status = "[green][OK] Good[/green]" if alloc_time < 0.1 else "[yellow][WARN] Slow[/yellow]"
            table.add_row("Memory Allocation", f"{alloc_time:.3f}s", status)

            del data  # Free memory

        except Exception as e:
            table.add_row("Memory Allocation", f"Error: {e}", "[red][FAIL] Failed[/red]")

    console.print(table)


@app.command()
def security():
    """Check security-related settings and configurations"""
    console.print("\n[bold cyan]🔒 Security Check[/bold cyan]\n")

    issues = []
    warnings = []

    # Check if running as root
    if os.geteuid() == 0:
        issues.append("Running as root user - not recommended for security")

    # Check file permissions
    home = Path.home()

    # SSH directory permissions
    ssh_dir = home / ".ssh"
    if ssh_dir.exists():
        mode = oct(ssh_dir.stat().st_mode)[-3:]
        if mode != "700":
            issues.append(f"SSH directory permissions are {mode}, should be 700")

    # Check for world-writable files in home
    try:
        for item in home.iterdir():
            if item.is_file():
                mode = item.stat().st_mode
                if mode & 0o002:  # world-writable
                    warnings.append(f"World-writable file: {item.name}")
    except PermissionError:
        warnings.append("Cannot check home directory permissions")

    # Check core dump settings
    try:
        with open("/proc/sys/kernel/core_pattern", "r") as f:
            core_pattern = f.read().strip()
            if core_pattern != "/dev/null":
                warnings.append("Core dumps are enabled - may leak sensitive data")
    except FileNotFoundError:
        pass  # Not Linux

    # Check OFX secrets directory
    if HAS_OFX_CONFIG:
        from ofx.settings import SECRETS_DIR
        if SECRETS_DIR.exists():
            mode = oct(SECRETS_DIR.stat().st_mode)[-3:]
            if mode != "700":
                issues.append(f"OFX secrets directory permissions are {mode}, should be 700")

    # Check for sensitive files with wrong permissions
    sensitive_files = [".env", "secrets.enc", ".git/config"]
    for filename in sensitive_files:
        filepath = Path(filename)
        if filepath.exists():
            mode = oct(filepath.stat().st_mode)[-3:]
            if mode not in ["600", "700"]:
                warnings.append(f"Sensitive file {filename} has permissions {mode}")

    # Display results
    if issues:
        console.print("[bold red]Critical Issues:[/bold red]")
        for issue in issues:
            console.print(f"  [red][FAIL] {issue}[/red]")
        console.print()

    if warnings:
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in warnings:
            console.print(f"  [yellow][WARN] {warning}[/yellow]")
        console.print()

    if not issues and not warnings:
        console.print("[green][OK] No security issues detected[/green]")
    elif issues:
        console.print("[red][WARN] Address critical security issues before using OFX[/red]")
    else:
        console.print("[yellow][WARN] Review warnings for better security[/yellow]")


@app.command()
def resources():
    """Check system resources (CPU, memory, disk)"""
    console.print("\n[bold cyan]💻 System Resources[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Resource", style="cyan", width=15)
    table.add_column("Status", width=10)
    table.add_column("Current", width=20)
    table.add_column("Details", width=35)

    # CPU Info
    try:
        if HAS_PSUTIL:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_status = "[green][OK] OK[/green]" if cpu_percent < 80 else "[red][FAIL] High[/red]"
            table.add_row("CPU Usage", cpu_status, f"{cpu_percent:.1f}%", f"{cpu_count} cores")
        else:
            table.add_row("CPU Usage", "[yellow][SKIP] Unknown[/yellow]", "N/A", "Install psutil for details")
    except Exception as e:
        table.add_row("CPU Usage", "[red][FAIL] Error[/red]", "N/A", str(e))

    # Memory Info
    mem_ok, mem_msg, mem_metrics = check_memory()
    mem_status = "[green][OK] OK[/green]" if mem_ok else "[red][FAIL] Low[/red]"
    table.add_row("Memory", mem_status, "N/A", mem_msg)

    # Disk Space
    disk_ok, disk_msg, disk_metrics = check_disk_space()
    disk_status = "[green][OK] OK[/green]" if disk_ok else "[red][FAIL] Low[/red]"
    table.add_row("Disk Space", disk_status, "N/A", disk_msg)

    # OFX Data Directory
    ofx_data_ok, ofx_data_msg, ofx_metrics = check_disk_space(BASE_DATA_DIR)
    ofx_status = "[green][OK] OK[/green]" if ofx_data_ok else "[red][FAIL] Low[/red]"
    table.add_row("OFX Data Dir", ofx_status, "N/A", ofx_data_msg)

    console.print(table)

    # Additional system info
    if HAS_PSUTIL:
        try:
            import psutil
            console.print("\n[bold]Detailed System Info:[/bold]")

            # CPU details
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                console.print(f"CPU Frequency: {cpu_freq.current:.0f}MHz (max: {cpu_freq.max:.0f}MHz)")

            # Load average
            load = psutil.getloadavg()
            console.print(f"Load Average: {load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}")

            # Uptime
            uptime = time.time() - psutil.boot_time()
            uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))
            console.print(f"System Uptime: {uptime_str}")

        except Exception as e:
            console.print(f"[yellow]Could not get detailed system info: {e}[/yellow]")


@app.command()
def metrics(
    interval: float = typer.Option(1.0, help="Measurement interval in seconds"),
    show_processes: bool = typer.Option(False, help="Show top processes"),
    show_network: bool = typer.Option(False, help="Show network statistics"),
):
    """Display detailed system metrics and performance indicators"""
    console.print("\n[bold cyan]📊 System Metrics Dashboard[/bold cyan]\n")

    # CPU Metrics
    console.print("[bold]CPU Metrics:[/bold]")
    cpu_table = Table(show_header=True, header_style="bold magenta")
    cpu_table.add_column("Metric", style="cyan", width=20)
    cpu_table.add_column("Value", width=25)
    cpu_table.add_column("Status", width=15)

    if HAS_PSUTIL:
        try:
            import psutil

            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=interval)
            cpu_count = psutil.cpu_count()
            cpu_count_logical = psutil.cpu_count(logical=True)

            cpu_status = "[green][OK] Normal[/green]" if cpu_percent < 80 else "[red][WARN] High[/red]"
            cpu_table.add_row("CPU Usage", f"{cpu_percent:.1f}%", cpu_status)
            cpu_table.add_row("Physical Cores", str(cpu_count), "[green][OK] OK[/green]")
            cpu_table.add_row("Logical Cores", str(cpu_count_logical), "[green][OK] OK[/green]")

            # CPU frequency
            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                cpu_table.add_row("CPU Frequency", f"{cpu_freq.current:.0f} MHz", "[green][OK] OK[/green]")
                cpu_table.add_row("CPU Max Freq", f"{cpu_freq.max:.0f} MHz", "[green][OK] OK[/green]")

            # Load average
            load = psutil.getloadavg()
            cpu_cores = cpu_count_logical or cpu_count or 1  # fallback to 1 if both are None
            load_status = "[green][OK] Normal[/green]" if load[0] < cpu_cores else "[yellow][WARN] High[/yellow]"
            cpu_table.add_row("Load Average", f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}", load_status)

        except Exception as e:
            cpu_table.add_row("CPU Metrics", f"Error: {e}", "[red]✗ Failed[/red]")
    else:
        cpu_table.add_row("CPU Metrics", "psutil not available", "[yellow]○ Limited[/yellow]")

    console.print(cpu_table)

    # Memory Metrics
    console.print("\n[bold]Memory Metrics:[/bold]")
    mem_table = Table(show_header=True, header_style="bold magenta")
    mem_table.add_column("Metric", style="cyan", width=20)
    mem_table.add_column("Value", width=25)
    mem_table.add_column("Status", width=15)

    mem_ok, mem_msg, mem_metrics = check_memory()
    if mem_metrics:
        mem_table.add_row("Total RAM", f"{mem_metrics['total_gb']:.1f} GB", "[green][OK] OK[/green]")
        mem_table.add_row("Used RAM", f"{mem_metrics['used_gb']:.1f} GB", "[green][OK] OK[/green]")
        mem_table.add_row("Available RAM", f"{mem_metrics['available_gb']:.1f} GB", "[green][OK] OK[/green]")
        mem_table.add_row("RAM Usage", f"{mem_metrics['percent_used']:.1f}%",
                         "[green][OK] OK[/green]" if mem_metrics['percent_used'] < 80 else "[red][WARN] High[/red]")

        if mem_metrics.get('swap_total_gb', 0) > 0:
            mem_table.add_row("Total Swap", f"{mem_metrics['swap_total_gb']:.1f} GB", "[green][OK] OK[/green]")
            mem_table.add_row("Used Swap", f"{mem_metrics['swap_used_gb']:.1f} GB", "[green][OK] OK[/green]")
            mem_table.add_row("Swap Usage", f"{mem_metrics['swap_percent']:.1f}%",
                             "[green][OK] OK[/green]" if mem_metrics['swap_percent'] < 50 else "[yellow][WARN] High[/yellow]")
    else:
        mem_table.add_row("Memory Metrics", mem_msg, "[yellow][SKIP] Limited[/yellow]")

    console.print(mem_table)

    # Disk Metrics
    console.print("\n[bold]Disk Metrics:[/bold]")
    disk_table = Table(show_header=True, header_style="bold magenta")
    disk_table.add_column("Metric", style="cyan", width=20)
    disk_table.add_column("Value", width=25)
    disk_table.add_column("Status", width=15)

    disk_ok, disk_msg, disk_metrics = check_disk_space()
    if disk_metrics:
        disk_table.add_row("Total Space", f"{disk_metrics['total_gb']:.1f} GB", "[green][OK] OK[/green]")
        disk_table.add_row("Used Space", f"{disk_metrics['used_gb']:.1f} GB", "[green][OK] OK[/green]")
        disk_table.add_row("Free Space", f"{disk_metrics['free_gb']:.1f} GB", "[green][OK] OK[/green]")
        disk_table.add_row("Usage", f"{disk_metrics['used_percent']:.1f}%",
                          "[green][OK] OK[/green]" if disk_metrics['used_percent'] < 90 else "[red][WARN] High[/red]")
    else:
        disk_table.add_row("Disk Metrics", disk_msg, "[yellow][SKIP] Limited[/yellow]")

    console.print(disk_table)

    # Network Metrics
    if show_network and HAS_PSUTIL:
        console.print("\n[bold]Network Metrics:[/bold]")
        net_table = Table(show_header=True, header_style="bold magenta")
        net_table.add_column("Interface", style="cyan", width=15)
        net_table.add_column("Status", width=10)
        net_table.add_column("Sent", width=15)
        net_table.add_column("Received", width=15)

        try:
            import psutil
            net_stats = psutil.net_if_stats()
            net_io = psutil.net_io_counters(pernic=True)

            for interface, stats in net_stats.items():
                if stats.isup:
                    io_stats = net_io.get(interface)
                    if io_stats:
                        sent_mb = io_stats.bytes_sent / (1024**2)
                        recv_mb = io_stats.bytes_recv / (1024**2)
                        net_table.add_row(
                            interface,
                            "[green]✓ Up[/green]",
                            f"{sent_mb:.1f} MB",
                            f"{recv_mb:.1f} MB"
                        )
                    else:
                        net_table.add_row(interface, "[green]✓ Up[/green]", "N/A", "N/A")
                else:
                    net_table.add_row(interface, "[red]✗ Down[/red]", "N/A", "N/A")

        except Exception as e:
            net_table.add_row("Network", f"Error: {e}", "[red]✗ Failed[/red]", "N/A")

        console.print(net_table)

    # Process Information
    if show_processes and HAS_PSUTIL:
        console.print("\n[bold]Top Processes (by CPU):[/bold]")
        proc_table = Table(show_header=True, header_style="bold magenta")
        proc_table.add_column("PID", style="cyan", width=8)
        proc_table.add_column("Name", width=20)
        proc_table.add_column("CPU %", width=10)
        proc_table.add_column("Memory %", width=12)
        proc_table.add_column("Status", width=15)

        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
                try:
                    proc_info = proc.info
                    if proc_info['cpu_percent'] is not None:
                        processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU usage and show top 10
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            for proc in processes[:10]:
                status_color = {
                    psutil.STATUS_RUNNING: "[green]Running[/green]",
                    psutil.STATUS_SLEEPING: "[yellow]Sleeping[/yellow]",
                    psutil.STATUS_STOPPED: "[red]Stopped[/red]",
                    psutil.STATUS_ZOMBIE: "[red]Zombie[/red]",
                }.get(proc['status'], f"[gray]{proc['status']}[/gray]")

                proc_table.add_row(
                    str(proc['pid']),
                    proc['name'][:19],
                    f"{proc['cpu_percent']:.1f}",
                    f"{proc['memory_percent']:.1f}",
                    status_color
                )

        except Exception as e:
            proc_table.add_row("Processes", f"Error: {e}", "[red]✗ Failed[/red]", "N/A", "N/A")

        console.print(proc_table)

    # System Information Summary
    console.print("\n[bold]System Summary:[/bold]")
    summary_table = Table(show_header=False)
    summary_table.add_column("Property", style="cyan", width=20)
    summary_table.add_column("Value", width=50)

    summary_table.add_row("Platform", platform.platform())
    summary_table.add_row("Architecture", platform.machine())
    summary_table.add_row("Python Version", sys.version.split()[0])

    if HAS_PSUTIL:
        try:
            import psutil
            uptime = time.time() - psutil.boot_time()
            uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))
            summary_table.add_row("System Uptime", uptime_str)
            summary_table.add_row("Boot Time", time.ctime(psutil.boot_time()))
        except:
            pass

    console.print(summary_table)


@app.command()
def install_help(
    tool: Optional[str] = typer.Argument(
        None, help="Specific tool to show installation help for"
    ),
):
    """Show installation instructions for tools"""
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
