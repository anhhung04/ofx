from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .project_manager import ProjectManager

console = Console()

app = typer.Typer()


NAME = "project"

HELP = "Manage Red Team projects."


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Project name")],
    is_multiphase: Annotated[
        bool,
        typer.Option("--multiphase", "-m", help="Initialize a multi-phase project"),
    ] = False,
):
    """Init new OFX project"""
    base = ProjectManager.create_project(name)
    console.print(f"[bold green]✓[/] Creating project: [cyan]{name}[/]")
    console.print(f"[dim]Location: {base}[/]")

    from ofx.commands.project.init import InitHandler

    console.print("\n[bold]Remote Storage Setup[/]")
    setup_remote = typer.confirm(
        "Would you like to set up remote storage?", default=True
    )

    remote_type = None
    remote_config = None
    encrypt = False
    encryption_key = None

    if setup_remote:
        console.print("\n[cyan]Available storage types:[/] git, ssh, s3, webdav, none")
        remote_type = typer.prompt("Select remote storage type", default="git")

        if remote_type not in ["git", "ssh", "s3", "webdav", "none"]:
            console.print(f"[red]Invalid storage type: {remote_type}[/]")
            remote_type = None
        elif remote_type == "git":
            git_url = typer.prompt("Enter Git repository URL")
            remote_config = {"url": git_url, "branch": "main"}

            console.print("\n[bold]Encryption Setup[/]")
            encrypt = typer.confirm(
                "Enable encryption for files in git repository?", default=False
            )
            if encrypt:
                encryption_key = typer.prompt(
                    "Enter encryption key (or press Enter to generate one)",
                    default="",
                    show_default=False,
                )
                if not encryption_key:
                    import secrets

                    encryption_key = secrets.token_urlsafe(32)
                    console.print(
                        f"\n[yellow]Generated encryption key:[/] {encryption_key}"
                    )
                    console.print(
                        "[yellow]⚠️  Save this key securely! You'll need it to decrypt files.[/]"
                    )
        elif remote_type == "ssh":
            ssh_host = typer.prompt("Enter SSH host (e.g., example.com)")
            ssh_user = typer.prompt("Enter SSH username")
            ssh_path = typer.prompt("Enter remote path", default="/home/backup")
            ssh_port = typer.prompt("Enter SSH port", default="22")
            remote_config = {
                "host": ssh_host,
                "user": ssh_user,
                "remote_path": ssh_path,
                "port": int(ssh_port),
            }

            console.print("\n[bold]Encryption Setup[/]")
            encrypt = typer.confirm("Enable encryption for synced files?", default=True)
            if encrypt:
                encryption_key = typer.prompt(
                    "Enter encryption key (or press Enter to generate one)",
                    default="",
                    show_default=False,
                )
                if not encryption_key:
                    import secrets

                    encryption_key = secrets.token_urlsafe(32)
                    console.print(
                        f"\n[yellow]Generated encryption key:[/] {encryption_key}"
                    )
                    console.print(
                        "[yellow]⚠️  Save this key securely! You'll need it to decrypt files.[/]"
                    )
        elif remote_type == "s3":
            bucket = typer.prompt("Enter S3 bucket name")
            region = typer.prompt("Enter AWS region", default="us-east-1")
            remote_config = {"bucket": bucket, "region_name": region}

            console.print("\n[bold]Encryption Setup[/]")
            encrypt = typer.confirm(
                "Enable encryption for synced files?", default=False
            )
            if encrypt:
                encryption_key = typer.prompt(
                    "Enter encryption key (or press Enter to generate one)",
                    default="",
                    show_default=False,
                )
                if not encryption_key:
                    import secrets

                    encryption_key = secrets.token_urlsafe(32)
                    console.print(
                        f"\n[yellow]Generated encryption key:[/] {encryption_key}"
                    )
                    console.print(
                        "[yellow]⚠️  Save this key securely! You'll need it to decrypt files.[/]"
                    )
        elif remote_type == "webdav":
            webdav_url = typer.prompt("Enter WebDAV URL")
            username = typer.prompt("Enter username", default="")
            password = typer.prompt("Enter password", default="", hide_input=True)
            remote_config = {
                "webdav_hostname": webdav_url,
                "webdav_login": username,
                "webdav_password": password,
            }

            console.print("\n[bold]Encryption Setup[/]")
            encrypt = typer.confirm(
                "Enable encryption for synced files?", default=False
            )
            if encrypt:
                encryption_key = typer.prompt(
                    "Enter encryption key (or press Enter to generate one)",
                    default="",
                    show_default=False,
                )
                if not encryption_key:
                    import secrets

                    encryption_key = secrets.token_urlsafe(32)
                    console.print(
                        f"\n[yellow]Generated encryption key:[/] {encryption_key}"
                    )
                    console.print(
                        "[yellow]⚠️  Save this key securely! You'll need it to decrypt files.[/]"
                    )
        elif remote_type == "none":
            remote_type = None

    InitHandler(
        base, is_multiphase, remote_type, remote_config, encrypt, encryption_key
    ).run()

    console.print(
        Panel(
            f"[bold green]Project '{name}' initialized successfully![/]",
            border_style="green",
        )
    )


@app.command()
def sync(
    project: Annotated[
        str,
        typer.Argument(help="Project name or path"),
    ],
    remote_type: Annotated[
        str,
        typer.Option(
            "--remote-type",
            "-t",
            help="Remote storage type: git (default), ssh, s3, webdav",
        ),
    ] = "git",
    remote_config: Annotated[
        Optional[str],
        typer.Option("--remote-config", "-c", help="Remote config as JSON"),
    ] = None,
    encrypt: Annotated[
        bool,
        typer.Option("--encrypt", "-e", help="Encrypt files before syncing"),
    ] = False,
    encryption_key: Annotated[
        Optional[str],
        typer.Option(
            "--encryption-key",
            help="Encryption key (or set OFX_ENCRYPTION_KEY env var)",
        ),
    ] = None,
):
    """Sync local project with remote storage (git by default)"""
    path = ProjectManager.resolve_path(project)
    console.print(f"[bold blue]⟳[/] Syncing project: [cyan]{project}[/]")
    console.print(f"[dim]Remote type: {remote_type}[/]")
    if encrypt:
        console.print("[dim]Encryption: enabled[/]")

    from ofx.commands.project.sync import SyncProjectHandler

    SyncProjectHandler(
        path,
        remote_type=remote_type,
        remote_config=remote_config,
        encrypt=encrypt,
        encryption_key=encryption_key,
    ).run()

    console.print("[bold green]✓[/] Sync completed successfully")


@app.command(name="list")
@app.command(name="ls", hidden=True)
def list():
    """List all projects in default project path"""
    projects = ProjectManager.list_projects()

    if not projects:
        console.print("[yellow]No projects found.[/]")
        console.print(f"[dim]Default path: {ProjectManager._get_default_path()}[/]")
        return

    table = Table(
        title=f"OFX Projects ({len(projects)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Project Name", style="cyan")
    table.add_column("Path", style="dim")

    for idx, p in enumerate(projects, 1):
        full_path = ProjectManager._get_default_path() / p
        table.add_row(str(idx), p, str(full_path))

    console.print(table)


@app.command(name="remove")
@app.command(name="rm", hidden=True)
def remove(name: Annotated[str, typer.Argument(help="Project name to delete")]):
    """Remove a project by name"""
    project_path = ProjectManager._get_default_path() / name

    if not project_path.exists():
        console.print(f"[red]✗[/] Project not found: [yellow]{name}[/]")
        return

    console.print(f"[yellow]⚠[/]  About to delete project: [red]{name}[/]")
    console.print(f"[dim]Path: {project_path}[/]")

    if not typer.confirm("Are you sure?"):
        console.print("[yellow]Deletion cancelled.[/]")
        return

    ok = ProjectManager.delete_project(name)
    if ok:
        console.print(f"[bold green]✓[/] Deleted project: [cyan]{name}[/]")
    else:
        console.print(f"[red]✗[/] Failed to delete project: [yellow]{name}[/]")


@app.command(hidden=True)
def encrypt_filter():
    """Git clean filter: Encrypt stdin to stdout (used by git attributes)"""
    import sys
    from pathlib import Path

    try:
        current = Path.cwd()
        key_file = None

        check_dirs = [current]
        check_dirs.extend(current.parents)

        for parent in check_dirs:
            candidate = parent / ".ofx-encryption-key"
            if candidate.exists():
                key_file = candidate
                break

        if not key_file:
            sys.stdout.buffer.write(sys.stdin.buffer.read())
            return

        encryption_key = key_file.read_text().strip()

        data = sys.stdin.buffer.read()

        from .storage import EncryptionHandler

        encryptor = EncryptionHandler(encryption_key)
        encrypted = encryptor.encrypt_data(data)

        sys.stdout.buffer.write(encrypted)
    except Exception:
        sys.stdout.buffer.write(sys.stdin.buffer.read())


@app.command(hidden=True)
def decrypt_filter():
    """Git smudge filter: Decrypt stdin to stdout (used by git attributes)"""
    import sys
    from pathlib import Path

    try:
        current = Path.cwd()
        key_file = None

        check_dirs = [current]
        check_dirs.extend(current.parents)

        for parent in check_dirs:
            candidate = parent / ".ofx-encryption-key"
            if candidate.exists():
                key_file = candidate
                break

        if not key_file:
            sys.stdout.buffer.write(sys.stdin.buffer.read())
            return

        encryption_key = key_file.read_text().strip()

        data = sys.stdin.buffer.read()

        if len(data) < 13:
            sys.stdout.buffer.write(data)
            return

        from .storage import EncryptionHandler

        encryptor = EncryptionHandler(encryption_key)
        decrypted = encryptor.decrypt_file(data)

        sys.stdout.buffer.write(decrypted)
    except Exception:
        sys.stdout.buffer.write(sys.stdin.buffer.read())
