"""Handler for `ofx flow diff` — compare two workflow structures."""

from __future__ import annotations

from rich.table import Table
from rich.tree import Tree

from ofx.commands.flow.info import _find_workflow_fuzzy, _step_type_label
from ofx.settings import get_console


def _diff_dicts(a: dict, b: dict, label: str) -> list[tuple[str, str, str]]:
    """Compare two dicts, return list of (key, status, detail) tuples."""
    rows: list[tuple[str, str, str]] = []
    all_keys = sorted(set(a) | set(b))
    for k in all_keys:
        if k not in a:
            rows.append((k, "[green]+ added[/]", str(b[k])[:60]))
        elif k not in b:
            rows.append((k, "[red]- removed[/]", str(a[k])[:60]))
        elif str(a[k]) != str(b[k]):
            rows.append(
                (k, "[yellow]~ changed[/]", f"{str(a[k])[:30]} → {str(b[k])[:30]}")
            )
    return rows


def _diff_lists(a: list, b: list) -> tuple[list, list, list]:
    """Return (added, removed, common) items."""
    sa, sb = set(a), set(b)
    return sorted(sb - sa), sorted(sa - sb), sorted(sa & sb)


def show_diff(name_a: str, name_b: str) -> None:
    """Compare two workflows and display structural differences."""
    console = get_console()

    try:
        wf_a = _find_workflow_fuzzy(name_a)
    except Exception as e:
        from ofx.commands.ui_helpers import error_exit

        error_exit("Workflow Not Found", str(e))

    try:
        wf_b = _find_workflow_fuzzy(name_b)
    except Exception as e:
        from ofx.commands.ui_helpers import error_exit

        error_exit("Workflow Not Found", str(e))

    has_diff = False

    # ── Overview ──
    overview = Table(
        title=f"Diff: {wf_a.name} ↔ {wf_b.name}",
        title_style="bold",
        padding=(0, 1),
    )
    overview.add_column("Field", style="cyan")
    overview.add_column(name_a, style="white")
    overview.add_column(name_b, style="white")
    overview.add_column("Status", no_wrap=True)

    fields = [
        ("name", wf_a.name, wf_b.name),
        (
            "description",
            wf_a.description.split("\n")[0][:60],
            wf_b.description.split("\n")[0][:60],
        ),
        ("tags", ", ".join(sorted(wf_a.tags)), ", ".join(sorted(wf_b.tags))),
        ("jobs", str(len(wf_a.jobs)), str(len(wf_b.jobs))),
        (
            "steps",
            str(sum(len(j.steps) for j in wf_a.jobs.values())),
            str(sum(len(j.steps) for j in wf_b.jobs.values())),
        ),
        ("tools", str(len(wf_a.tools)), str(len(wf_b.tools))),
        ("outputs", str(len(wf_a.outputs)), str(len(wf_b.outputs))),
    ]

    for label, va, vb in fields:
        if va != vb:
            has_diff = True
            overview.add_row(label, va, vb, "[yellow]~[/]")
        else:
            overview.add_row(label, va, vb, "[dim]=[/]")

    console.print(overview)
    console.print()

    # ── Tags diff ──
    added_tags, removed_tags, _ = _diff_lists(
        [t.lower() for t in wf_a.tags], [t.lower() for t in wf_b.tags]
    )
    if added_tags or removed_tags:
        has_diff = True
        tag_parts: list[str] = []
        if added_tags:
            tag_parts.append("[green]+ " + ", ".join(added_tags) + "[/]")
        if removed_tags:
            tag_parts.append("[red]- " + ", ".join(removed_tags) + "[/]")
        console.print(f"[bold]Tags:[/] {' '.join(tag_parts)}")
        console.print()

    # ── Jobs diff ──
    added_jobs, removed_jobs, common_jobs = _diff_lists(
        list(wf_a.jobs.keys()), list(wf_b.jobs.keys())
    )

    tree = Tree("[bold]Jobs[/bold]")

    if added_jobs:
        has_diff = True
        for jid in added_jobs:
            job_b = wf_b.jobs[jid]
            tree.add(f"[green]+ {jid}[/] ({len(job_b.steps)} steps)")

    if removed_jobs:
        has_diff = True
        for jid in removed_jobs:
            job_a = wf_a.jobs[jid]
            tree.add(f"[red]- {jid}[/] ({len(job_a.steps)} steps)")

    for jid in common_jobs:
        job_a = wf_a.jobs[jid]
        job_b = wf_b.jobs[jid]
        changes: list[str] = []

        # Compare job fields
        if job_a.name != job_b.name:
            changes.append(f"name: {job_a.name} → {job_b.name}")
        needs_a = sorted(
            job_a.needs if isinstance(job_a.needs, list) else [job_a.needs]
        )
        needs_b = sorted(
            job_b.needs if isinstance(job_b.needs, list) else [job_b.needs]
        )
        if needs_a != needs_b:
            changes.append(f"needs: {needs_a} → {needs_b}")
        if len(job_a.steps) != len(job_b.steps):
            changes.append(f"steps: {len(job_a.steps)} → {len(job_b.steps)}")
        if bool(job_a.strategy) != bool(job_b.strategy):
            changes.append("strategy changed")
        if bool(job_a.cloud) != bool(job_b.cloud):
            changes.append("cloud changed")
        if set(job_a.outputs.keys()) != set(job_b.outputs.keys()):
            changes.append("outputs changed")

        if changes:
            has_diff = True
            job_branch = tree.add(f"[yellow]~ {jid}[/]")
            for c in changes:
                job_branch.add(f"[dim]{c}[/]")

            # Step-level diff
            steps_a = {s.name: s for s in job_a.steps}
            steps_b = {s.name: s for s in job_b.steps}
            added_s, removed_s, common_s = _diff_lists(
                list(steps_a.keys()), list(steps_b.keys())
            )
            for sn in added_s:
                job_branch.add(
                    f"  [green]+ step: {sn}[/] ({_step_type_label(steps_b[sn])})"
                )
            for sn in removed_s:
                job_branch.add(
                    f"  [red]- step: {sn}[/] ({_step_type_label(steps_a[sn])})"
                )
            for sn in common_s:
                sa, sb = steps_a[sn], steps_b[sn]
                step_changes: list[str] = []
                if sa.get_run_type() != sb.get_run_type():
                    step_changes.append(
                        f"type: {sa.get_run_type().name} → {sb.get_run_type().name}"
                    )
                if sa.timeout != sb.timeout:
                    step_changes.append(f"timeout: {sa.timeout} → {sb.timeout}")
                if sa.continue_on_error != sb.continue_on_error:
                    step_changes.append(
                        f"continue-on-error: {sa.continue_on_error} → {sb.continue_on_error}"
                    )
                if sa.retry != sb.retry:
                    step_changes.append(f"retry: {sa.retry} → {sb.retry}")
                if step_changes:
                    step_branch = job_branch.add(f"  [yellow]~ step: {sn}[/]")
                    for sc in step_changes:
                        step_branch.add(f"    [dim]{sc}[/]")
        else:
            tree.add(f"[dim]= {jid}[/] ({len(job_a.steps)} steps)")

    console.print(tree)
    console.print()

    # ── Env diff ──
    env_rows = _diff_dicts(wf_a.env, wf_b.env, "env")
    if env_rows:
        has_diff = True
        env_table = Table(title="Environment Variables", padding=(0, 1))
        env_table.add_column("Variable", style="cyan")
        env_table.add_column("Status", no_wrap=True)
        env_table.add_column("Detail", style="dim")
        for k, status, detail in env_rows:
            env_table.add_row(k, status, detail)
        console.print(env_table)
        console.print()

    # ── Tools diff ──
    tools_a = {k: str(v) for k, v in wf_a.tools.items()}
    tools_b = {k: str(v) for k, v in wf_b.tools.items()}
    tool_rows = _diff_dicts(tools_a, tools_b, "tools")
    if tool_rows:
        has_diff = True
        tool_table = Table(title="Tools", padding=(0, 1))
        tool_table.add_column("Tool", style="cyan")
        tool_table.add_column("Status", no_wrap=True)
        tool_table.add_column("Detail", style="dim")
        for k, status, detail in tool_rows:
            tool_table.add_row(k, status, detail)
        console.print(tool_table)
        console.print()

    if not has_diff:
        console.print("[green bold]✓ Workflows are identical[/]")
