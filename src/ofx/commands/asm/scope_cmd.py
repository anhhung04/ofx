"""ASM scope commands — manage scopes, targets, and exclude rules."""

from typing import Annotated

import typer
from rich.table import Table

from ofx.settings import get_console

scope_app = typer.Typer(no_args_is_help=True, help="Manage ASM scopes and targets")


# ------------------------------------------------------------------
# ofx asm scope list
# ------------------------------------------------------------------


@scope_app.command("list")
def scope_list(
    group: Annotated[str, typer.Option("--group", "-g", help="Filter by group")] = "",
):
    """List all scopes on the ASM server."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scopes = client.list_scopes(group=group)

    if not scopes:
        console.print("[dim]No scopes found.[/dim]")
        return

    table = Table(title="ASM Scopes")
    table.add_column("ID", style="dim", max_width=36)
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Group")
    table.add_column("Description", max_width=40)

    for s in scopes:
        table.add_row(s.id, s.name, s.scope_type, s.group, s.description)

    console.print(table)


# ------------------------------------------------------------------
# ofx asm scope show
# ------------------------------------------------------------------


@scope_app.command("show")
def scope_show(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")],
):
    """Show details of a specific scope including target/asset counts."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)
    s = client.get_scope(scope_id)

    from rich.panel import Panel

    targets = client.list_targets(scope_id)
    assets, meta = client.list_assets(scope_id, limit=1)
    findings, fmeta = client.list_findings(scope_id, limit=1)
    rules = client.list_exclude_rules(scope_id)

    info = (
        f"[bold]Name:[/bold] {s.name}\n"
        f"[bold]ID:[/bold] {s.id}\n"
        f"[bold]Type:[/bold] {s.scope_type}\n"
        f"[bold]Group:[/bold] {s.group or '-'}\n"
        f"[bold]Description:[/bold] {s.description or '-'}\n"
        f"\n"
        f"[bold]Targets:[/bold] {len(targets)}\n"
        f"[bold]Assets:[/bold] {meta.total}\n"
        f"[bold]Findings:[/bold] {fmeta.total}\n"
        f"[bold]Exclude Rules:[/bold] {len(rules)}"
    )
    console.print(Panel(info, title=f"Scope: {s.name}", border_style="cyan"))


# ------------------------------------------------------------------
# ofx asm scope create
# ------------------------------------------------------------------


@scope_app.command("create")
def scope_create(
    name: Annotated[str, typer.Argument(help="Scope name")],
    scope_type: Annotated[
        str, typer.Option("--type", "-t", help="Scope type")
    ] = "domain",
    description: Annotated[str, typer.Option("--desc", "-d", help="Description")] = "",
    group: Annotated[str, typer.Option("--group", "-g", help="Group name")] = "",
    set_default: Annotated[
        bool, typer.Option("--default", help="Set as default scope")
    ] = False,
):
    """Create a new scope on the ASM server."""
    console = get_console()
    from ofx.asm.config import get_asm_client, get_asm_config

    client = get_asm_client()
    s = client.create_scope(
        name, scope_type=scope_type, description=description, group=group
    )
    console.print(f"[green]✓ Created scope '{s.name}' (ID: {s.id})[/green]")

    if set_default:
        cfg = get_asm_config()
        cfg.default_scope = s.id
        console.print("[dim]Set as default scope.[/dim]")


# ------------------------------------------------------------------
# ofx asm scope delete
# ------------------------------------------------------------------


@scope_app.command("delete")
def scope_delete(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation")
    ] = False,
):
    """Delete a scope and all its data."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)

    if not force:
        s = client.get_scope(scope_id)
        if not typer.confirm(
            f"Delete scope '{s.name}' ({scope_id})? This is irreversible."
        ):
            raise typer.Abort()

    client.delete_scope(scope_id)
    console.print(f"[green]✓ Scope {scope_id} deleted.[/green]")


# ------------------------------------------------------------------
# ofx asm scope targets
# ------------------------------------------------------------------


@scope_app.command("targets")
def scope_targets(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    effective: Annotated[
        bool,
        typer.Option(
            "--effective", "-e", help="Show effective targets after exclude rules"
        ),
    ] = False,
    target_type: Annotated[
        str, typer.Option("--type", "-t", help="Filter by type")
    ] = "",
):
    """List targets in a scope."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)

    if effective:
        targets = client.effective_targets(scope_id)
        table = Table(title="Effective Targets")
        table.add_column("Value", style="cyan")
        table.add_column("Type")
        table.add_column("Excluded", justify="center")
        table.add_column("Excluded By")

        for t in targets:
            if target_type and t.target_type != target_type:
                continue
            table.add_row(
                t.value,
                t.target_type,
                "✗" if t.excluded else "✓",
                t.exclude_by or "",
            )
    else:
        raw = client.list_targets(scope_id)
        table = Table(title="Targets")
        table.add_column("ID", style="dim", max_width=36)
        table.add_column("Value", style="cyan")
        table.add_column("Type")
        table.add_column("Enabled", justify="center")

        for t in raw:
            if target_type and t.target_type != target_type:
                continue
            table.add_row(t.id, t.value, t.target_type, "✓" if t.enabled else "✗")

    console.print(table)


# ------------------------------------------------------------------
# ofx asm scope add-target
# ------------------------------------------------------------------


@scope_app.command("add-target")
def scope_add_target(
    targets: Annotated[
        list[str], typer.Argument(help="Target values (domains, IPs, CIDRs, URLs)")
    ],
    scope: Annotated[str, typer.Option("--scope", "-s", help="Scope ID or name")] = "",
    target_type: Annotated[
        str,
        typer.Option(
            "--type", "-t", help="Target type (auto-detected if not specified)"
        ),
    ] = "",
):
    """Add targets to a scope.

    Multiple targets can be specified. If a file path is given, reads
    targets from the file (one per line).
    """
    console = get_console()
    from pathlib import Path

    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)

    # Expand file arguments
    all_targets: list[str] = []
    for t in targets:
        p = Path(t)
        if p.is_file():
            all_targets.extend(
                line.strip() for line in p.read_text().splitlines() if line.strip()
            )
        else:
            all_targets.append(t)

    if not all_targets:
        console.print("[yellow]No targets to add.[/yellow]")
        return

    if len(all_targets) == 1 and target_type:
        result = client.add_target(scope_id, all_targets[0], target_type=target_type)
        console.print(
            f"[green]✓ Added target: {result.value} ({result.target_type})[/green]"
        )
    else:
        result = client.bulk_import_targets(scope_id, all_targets, auto_detect=True)
        console.print(
            f"[green]✓ Imported {result.imported} targets[/green]"
            + (f" [dim]({result.skipped} skipped)[/dim]" if result.skipped else "")
        )


# ------------------------------------------------------------------
# ofx asm scope exclude
# ------------------------------------------------------------------


@scope_app.command("exclude")
def scope_exclude(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
):
    """List exclude rules for a scope."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)
    rules = client.list_exclude_rules(scope_id)

    if not rules:
        console.print("[dim]No exclude rules configured.[/dim]")
        return

    table = Table(title="Exclude Rules")
    table.add_column("ID", style="dim", max_width=36)
    table.add_column("Type", style="cyan")
    table.add_column("Value")
    table.add_column("Description")
    table.add_column("Global", justify="center")

    for r in rules:
        table.add_row(
            r.id,
            r.rule_type,
            r.value,
            r.description,
            "✓" if r.scope_id is None else "",
        )
    console.print(table)


# ------------------------------------------------------------------
# ofx asm scope add-exclude
# ------------------------------------------------------------------


@scope_app.command("add-exclude")
def scope_add_exclude(
    value: Annotated[
        str, typer.Argument(help="Rule value (e.g. '*.internal.com', '10.0.0.0/8')")
    ],
    scope: Annotated[str, typer.Option("--scope", "-s", help="Scope ID or name")] = "",
    rule_type: Annotated[
        str,
        typer.Option("--type", "-t", help="Rule type: domain, ip, subnet, port, regex"),
    ] = "domain",
    description: Annotated[str, typer.Option("--desc", "-d", help="Description")] = "",
):
    """Add an exclude rule to a scope."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)
    r = client.add_exclude_rule(scope_id, rule_type, value, description=description)
    console.print(f"[green]✓ Added exclude rule: {r.rule_type} = {r.value}[/green]")


# ------------------------------------------------------------------
# ofx asm scope assets
# ------------------------------------------------------------------


@scope_app.command("assets")
def scope_assets(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    asset_type: Annotated[
        str, typer.Option("--type", "-t", help="Filter by asset type")
    ] = "",
    source: Annotated[
        str, typer.Option("--source", "-s", help="Filter by source")
    ] = "",
    search: Annotated[
        str, typer.Option("--search", "-q", help="Free-text search")
    ] = "",
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 50,
):
    """List assets in a scope."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)
    assets, meta = client.list_assets(
        scope_id,
        limit=limit,
        asset_type=asset_type,
        source=source,
        search=search,
    )

    if not assets:
        console.print("[dim]No assets found.[/dim]")
        return

    table = Table(title=f"Assets ({meta.total} total)")
    table.add_column("Type", style="cyan")
    table.add_column("Value")
    table.add_column("Source")
    table.add_column("Alive", justify="center")
    table.add_column("CDN", justify="center")
    table.add_column("Status")

    for a in assets:
        table.add_row(
            a.asset_type,
            a.value[:80],
            a.source,
            "✓" if a.is_alive else ("✗" if a.is_alive is False else "?"),
            "✓" if a.is_cdn else ("✗" if a.is_cdn is False else ""),
            str(a.status_code) if a.status_code else "",
        )

    console.print(table)
    if meta.total > limit:
        console.print(
            f"[dim]Showing {limit} of {meta.total}. Use --limit to see more.[/dim]"
        )


# ------------------------------------------------------------------
# ofx asm scope findings
# ------------------------------------------------------------------


@scope_app.command("findings")
def scope_findings(
    scope: Annotated[str, typer.Argument(help="Scope ID or name")] = "",
    severity: Annotated[
        str, typer.Option("--severity", "-s", help="Filter by severity")
    ] = "",
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 50,
):
    """List findings in a scope."""
    console = get_console()
    from ofx.asm.config import get_asm_client

    client = get_asm_client()
    scope_id = _resolve_scope(client, scope)
    findings, meta = client.list_findings(scope_id, limit=limit, severity=severity)

    if not findings:
        console.print("[dim]No findings found.[/dim]")
        return

    severity_colors = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "cyan",
        "info": "dim",
    }

    table = Table(title=f"Findings ({meta.total} total)")
    table.add_column("Severity")
    table.add_column("Title")
    table.add_column("Type")
    table.add_column("Source")

    for f in findings:
        color = severity_colors.get(f.severity, "white")
        table.add_row(
            f"[{color}]{f.severity.upper()}[/{color}]",
            f.title[:60],
            f.finding_type,
            f.source,
        )

    console.print(table)
    if meta.total > limit:
        console.print(
            f"[dim]Showing {limit} of {meta.total}. Use --limit to see more.[/dim]"
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _resolve_scope(client, scope_ref: str) -> str:
    """Resolve scope by ID or name, falling back to default."""
    from ofx.asm.config import get_asm_config

    if not scope_ref:
        cfg = get_asm_config()
        scope_ref = cfg.default_scope
        if not scope_ref:
            get_console().print(
                "[red]No scope specified and no default scope configured.[/red]"
            )
            get_console().print(
                "Set a default: [bold]ofx asm config set --default-scope <ID>[/bold]"
            )
            raise typer.Exit(code=1)

    if len(scope_ref) >= 32 and "-" in scope_ref:
        return scope_ref

    found = client.find_scope(scope_ref)
    if found:
        return found.id

    get_console().print(f"[red]Scope '{scope_ref}' not found.[/red]")
    raise typer.Exit(code=1)
