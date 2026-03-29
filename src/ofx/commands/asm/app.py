"""ASM CLI — manage connection to the ASM platform.

Subcommands:
    config  — configure ASM server URL and API token
    scope   — list/create/show scopes, targets, and exclude rules
    push    — export OFX scan results to an ASM scope
    pull    — load scope targets for workflow input
    sync    — bidirectional sync (push results + pull new targets)
"""

from typing import Annotated

import typer

from ofx.commands.asm.config_cmd import config_app
from ofx.commands.asm.scope_cmd import scope_app
from ofx.settings import get_console

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)

NAME = "asm"
HELP = "Interact with the ASM platform"
ALIAS = ["a"]

app.add_typer(config_app, name="config")
app.add_typer(scope_app, name="scope")


# ------------------------------------------------------------------
# ofx asm push
# ------------------------------------------------------------------

@app.command("push")
def asm_push(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    output_dir: Annotated[str, typer.Option("--output", "-o", help="Path to OFX output directory with typed_outputs.json")] = "",
    source: Annotated[str, typer.Option("--source", "-s", help="Source label for imported assets")] = "ofx",
):
    """Push OFX scan results (typed outputs) to an ASM scope.

    Reads typed_outputs.json from the OFX output directory, converts
    assets and findings, then imports them into the specified ASM scope.
    """
    console = get_console()
    import json
    from pathlib import Path

    from ofx.asm.config import get_asm_client
    from ofx.asm.export import batch_convert

    client = get_asm_client()
    scope_id = _resolve_scope_id(client, scope)

    # Find typed outputs
    if output_dir:
        base = Path(output_dir)
    else:
        base = Path.cwd()

    candidates = [
        base / "typed_outputs.json",
        base / "findings" / "typed_outputs.json",
    ]
    typed_path = None
    for c in candidates:
        if c.exists():
            typed_path = c
            break

    if not typed_path:
        # Try to collect from all json files in findings subdirectories
        items = _collect_from_findings_dir(base)
        if not items:
            console.print("[red]No typed_outputs.json found in output directory.[/red]")
            console.print(f"Searched: {', '.join(str(c) for c in candidates)}")
            raise typer.Exit(code=1)
    else:
        items = json.loads(typed_path.read_text())

    if not items:
        console.print("[yellow]No typed outputs to push.[/yellow]")
        return

    assets, findings = batch_convert(items, source=source)

    console.print(f"[dim]Converting {len(items)} typed outputs → {len(assets)} assets, {len(findings)} findings[/dim]")

    if assets:
        result = client.import_generic(scope_id, assets)
        imported = result.get("imported", 0)
        total = result.get("total", len(assets))
        console.print(f"[green]✓ Imported {imported}/{total} assets to scope {scope_id}[/green]")
    else:
        console.print("[dim]No assets to push.[/dim]")

    if findings:
        console.print(f"[yellow]⚠ {len(findings)} findings detected but ASM import endpoint handles assets only. Findings will be available when ASM adds finding import support.[/yellow]")


# ------------------------------------------------------------------
# ofx asm pull
# ------------------------------------------------------------------

@app.command("pull")
def asm_pull(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    effective: Annotated[bool, typer.Option("--effective", "-e", help="Show effective targets (after exclude rules)")] = False,
    output_file: Annotated[str, typer.Option("--output", "-o", help="Write targets to file (one per line)")] = "",
    target_type: Annotated[str, typer.Option("--type", "-t", help="Filter by target type (domain, ip, cidr, url)")] = "",
):
    """Pull targets from an ASM scope for use in OFX workflows.

    Without --output, prints targets to stdout (one per line) for
    piping into OFX or other tools. With --output, writes to a file.
    """
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope_id(client, scope)

    if effective:
        raw = client.effective_targets(scope_id)
        targets = [
            t for t in raw
            if not t.excluded and (not target_type or t.target_type == target_type)
        ]
        values = [t.value for t in targets]
    else:
        raw_targets = client.list_targets(scope_id)
        targets_list = [
            t for t in raw_targets
            if t.enabled and (not target_type or t.target_type == target_type)
        ]
        values = [t.value for t in targets_list]

    if not values:
        console.print("[yellow]No targets found.[/yellow]")
        return

    if output_file:
        from pathlib import Path

        Path(output_file).write_text("\n".join(values) + "\n")
        console.print(f"[green]✓ Wrote {len(values)} targets to {output_file}[/green]")
    else:
        for v in values:
            typer.echo(v)


# ------------------------------------------------------------------
# ofx asm sync
# ------------------------------------------------------------------

@app.command("sync")
def asm_sync(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    output_dir: Annotated[str, typer.Option("--output", "-o", help="OFX output directory to push")] = "",
    targets_file: Annotated[str, typer.Option("--targets-file", help="Write pulled targets to this file")] = "",
    source: Annotated[str, typer.Option("--source", "-s", help="Source label for imported assets")] = "ofx",
):
    """Bidirectional sync: push OFX results and pull updated targets.

    1. Pushes typed outputs from --output directory to the ASM scope.
    2. Pulls effective targets from the scope (after exclude rules).
    """
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope_id(client, scope)

    # Push phase
    console.print("[bold]Phase 1: Push results → ASM[/bold]")
    try:
        # Reuse push logic
        import sys
        sys.argv  # just to avoid unused import
        asm_push.callback(scope=scope_id, output_dir=output_dir, source=source)
    except SystemExit:
        pass

    # Pull phase
    console.print("\n[bold]Phase 2: Pull targets ← ASM[/bold]")
    asm_pull.callback(scope=scope_id, effective=True, output_file=targets_file, target_type="")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_scope_id(client, scope_ref: str) -> str:
    """Resolve a scope reference (ID or name) to scope ID."""
    from ofx.asm.config import get_asm_config

    if not scope_ref:
        cfg = get_asm_config()
        scope_ref = cfg.default_scope
        if not scope_ref:
            get_console().print("[red]No scope specified and no default scope configured.[/red]")
            get_console().print("Set a default: [bold]ofx asm config set --default-scope <ID>[/bold]")
            raise typer.Exit(code=1)

    # If it looks like a UUID, use directly
    if len(scope_ref) >= 32 and "-" in scope_ref:
        return scope_ref

    # Otherwise search by name
    found = client.find_scope(scope_ref)
    if found:
        return found.id

    get_console().print(f"[red]Scope '{scope_ref}' not found.[/red]")
    raise typer.Exit(code=1)


def _collect_from_findings_dir(base_path) -> list:
    """Try to collect typed outputs from JSON files in findings subdirectories."""
    import json
    from pathlib import Path

    items = []
    base = Path(base_path)

    # Look for JSON findings files in subdirectories
    for json_file in sorted(base.rglob("*.json")):
        if json_file.name == "typed_outputs.json":
            try:
                data = json.loads(json_file.read_text())
                if isinstance(data, list):
                    items.extend(data)
            except (json.JSONDecodeError, OSError):
                continue
    return items
