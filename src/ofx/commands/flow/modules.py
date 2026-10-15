"""CLI subcommands for ``ofx flow modules`` — manage namespaced remote modules.

Remote module refs use the ``<owner>.<repo>.<module>[@<ref>][::<func>]``
scheme; repos are cloned into ``~/.ofx/modules/<owner>/<repo>[@<ref>]``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ofx.commands.ui_helpers import print_info, print_success, print_warning
from ofx.modules import ModuleRegistry
from ofx.modules.refs import (
    REMOTE_KIND,
    ModuleRef,
    parse_module_ref,
    parse_remote_repo,
)
from ofx.modules.remote import (
    MANIFEST_FILENAME,
    cache_dir_for,
    clone_remote_module,
    ensure_remote_module,
    load_manifest,
    remove_cached_clone,
    update_cached_clone,
)
from ofx.settings import MODULES_DIR, get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def _parse_repo_ref(spec: str) -> ModuleRef:
    """Parse an ``<owner>.<repo>[@<ref>]`` argument into a remote ModuleRef."""
    try:
        return parse_remote_repo(spec)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def add(
    repo: Annotated[
        str,
        typer.Argument(
            help="'<owner>.<repo>[@<ref>]' module repo to pre-clone and cache."
        ),
    ],
    verify_manifest: Annotated[
        bool,
        typer.Option(
            "--verify-manifest/--no-verify-manifest",
            help="Validate ofx-modules.yml right after cloning (default: on).",
        ),
    ] = True,
):
    """Pre-clone a remote module repo into the local module cache."""
    ref = _parse_repo_ref(repo)
    try:
        target = clone_remote_module(ref)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if verify_manifest:
        try:
            load_manifest(ref, target)
        except Exception as exc:
            shutil.rmtree(target, ignore_errors=True)
            raise typer.BadParameter(str(exc)) from exc
    ref_label = f"@{ref.ref}" if ref.ref else ""
    print_success(
        "Added",
        f"Cached '{ref.owner}/{ref.repo}{ref_label}' at {target}",
    )


@app.command()
def update(
    repo: Annotated[
        str | None,
        typer.Argument(
            help="'<owner>.<repo>' clone to update (default: all unpinned clones)."
        ),
    ] = None,
):
    """Pull latest changes for unpinned cached module clones."""
    if repo:
        ref = _parse_repo_ref(repo)
        if ref.ref:
            raise typer.BadParameter(
                "Pinned clones are immutable; remove and re-add with the "
                "new ref instead of updating."
            )
        target = cache_dir_for(parse_remote_repo(f"{ref.owner}.{ref.repo}"))
        if not target.is_dir():
            print_warning("Not Found", f"No cached clone at {target}")
            raise typer.Exit(code=1)
        targets = [(f"{ref.owner}/{ref.repo}", target)]
    else:
        targets = _iter_cached_clones()
    if not targets:
        print_info("Modules", "No cached remote module clones found.")
        return
    updated: list[str] = []
    skipped: list[str] = []
    for label, target in targets:
        try:
            update_cached_clone(target)
            updated.append(label)
        except ValueError as exc:
            skipped.append(f"{label} ({exc})")
    if updated:
        print_success("Updated", f"Pulled {len(updated)} clone(s): {', '.join(updated)}")
    if skipped:
        print_warning("Skipped", "; ".join(skipped))


@app.command()
def remove(
    repo: Annotated[
        str,
        typer.Argument(help="'<owner>.<repo>[@<ref>]' cached clone to delete."),
    ],
):
    """Delete a cached remote module clone."""
    ref = _parse_repo_ref(repo)
    target = cache_dir_for(ref)
    try:
        removed = remove_cached_clone(target)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except FileNotFoundError as exc:
        print_warning("Not Found", str(exc))
        raise typer.Exit(code=1) from exc
    ref_label = f"@{ref.ref}" if ref.ref else ""
    print_success(
        "Removed", f"Deleted '{ref.owner}/{ref.repo}{ref_label}' from {removed}"
    )


@app.command("list")
def list_modules(
    show_local: Annotated[
        bool,
        typer.Option(
            "--local/--no-local",
            help="Include workflow-local modules/ (default: on).",
        ),
    ] = True,
):
    """List builtin modules, cached remote modules, and workflow-local modules."""
    console = get_console()
    table = Table(
        title=f"Modules (cache: {MODULES_DIR})",
        border_style="cyan",
        header_style="bold cyan",
    )
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold", no_wrap=True)
    table.add_column("Location", style="dim")

    for name in ModuleRegistry().builtin_names:
        table.add_row("builtin", name, "built-in")

    for name in ModuleRegistry().tool_names:
        table.add_row("tool", name, "built-in")

    for name in ModuleRegistry().library_names:
        table.add_row("library", name, "ofx.lib")

    for label, target in _iter_cached_clones():
        name = label.replace("/", ".")
        table.add_row("remote", name, str(target))

    if show_local:
        local_modules_dir = Path.cwd() / "modules"
        if local_modules_dir.is_dir():
            for module_file in sorted(local_modules_dir.glob("*.py")):
                table.add_row("local", module_file.stem, str(module_file))

    console.print(table)


def _iter_cached_clones() -> list[tuple[str, Path]]:
    """Yield ``(owner/repo[@ref], path)`` for every cached module clone."""
    clones: list[tuple[str, Path]] = []
    if not MODULES_DIR.is_dir():
        return clones
    for owner_dir in sorted(MODULES_DIR.iterdir()):
        if not owner_dir.is_dir() or owner_dir.name.startswith("."):
            continue
        for repo_dir in sorted(owner_dir.iterdir()):
            if repo_dir.is_dir() and not repo_dir.name.startswith("."):
                clones.append((f"{owner_dir.name}/{repo_dir.name}", repo_dir))
    return clones


@app.command()
def info(
    module: Annotated[
        str,
        typer.Argument(help="'<owner>.<repo>.<module>[@<ref>]' module to resolve."),
    ],
):
    """Show details for a module: remote spec, builtin, tool, or library module."""
    console = get_console()

    # Try registry resolution first (builtin, tool, library)
    from ofx.modules import ModuleRegistry

    registry = ModuleRegistry()
    spec = None
    for candidate in (module.strip(), f"local.builtin.{module.strip()}"):
        try:
            spec = registry.resolve(candidate)
            break
        except ValueError:
            continue

    if spec is not None:
        console.print(f"[bold]Module:[/bold] {spec.name}")
        console.print(f"[bold]Kind:[/bold] {spec.kind}")
        console.print(f"[bold]Description:[/bold] {spec.description or '(none)'}")
        if spec.args_schema:
            console.print("[bold]Arguments:[/bold]")
            for arg_name, arg_spec in spec.args_schema.items():
                req = " (required)" if arg_spec.get("required") else ""
                default = f" [default: {arg_spec['default']}]" if "default" in arg_spec else ""
                desc = arg_spec.get("description", "")
                console.print(f"  {arg_name}: {arg_spec.get('type', 'any')}{req}{default}  {desc}")
        else:
            console.print("[bold]Arguments:[/bold] (none)")
        return

    # Remote module
    ref = parse_module_ref(module.strip())
    if ref.kind != REMOTE_KIND:
        raise typer.BadParameter(
            f"Unknown module: '{module}'. Try 'ofx flow modules list' to see available modules."
        )
    try:
        entry = ensure_remote_module(ref)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[bold]Module:[/bold] {ref.raw}")
    if entry.api_path:
        console.print(f"[bold]Lib function:[/bold] ofx.lib.{entry.api_path}")
    else:
        console.print(f"[bold]File:[/bold] {entry.file}")
        console.print(f"[bold]Function:[/bold] {entry.function}")
    manifest_path = (
        (entry.file.parent.parent if entry.file else cache_dir_for(ref))
        / MANIFEST_FILENAME
    )
    console.print(f"[dim]Manifest: {manifest_path}[/dim]")
