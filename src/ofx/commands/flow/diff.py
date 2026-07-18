"""Handler for `ofx flow diff` — compare two workflow structures."""

from __future__ import annotations

from rich.table import Table
from rich.tree import Tree

from ofx.commands.flow.info import _find_workflow_fuzzy
from ofx.runner.step_descriptors import step_type_label
from ofx.settings import get_console

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

    tags_a = {tag.lower() for tag in wf_a.tags}
    tags_b = {tag.lower() for tag in wf_b.tags}
    added_tags = sorted(tags_b - tags_a)
    removed_tags = sorted(tags_a - tags_b)
    if added_tags or removed_tags:
        has_diff = True
        tag_parts: list[str] = []
        if added_tags:
            tag_parts.append("[green]+ " + ", ".join(added_tags) + "[/]")
        if removed_tags:
            tag_parts.append("[red]- " + ", ".join(removed_tags) + "[/]")
        console.print(f"[bold]Tags:[/] {' '.join(tag_parts)}")
        console.print()

    jobs_a = set(wf_a.jobs.keys())
    jobs_b = set(wf_b.jobs.keys())
    added_jobs = sorted(jobs_b - jobs_a)
    removed_jobs = sorted(jobs_a - jobs_b)
    common_jobs = sorted(jobs_a & jobs_b)

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

            steps_a = {s.name: s for s in job_a.steps}
            steps_b = {s.name: s for s in job_b.steps}
            step_names_a = set(steps_a.keys())
            step_names_b = set(steps_b.keys())
            added_s = sorted(step_names_b - step_names_a)
            removed_s = sorted(step_names_a - step_names_b)
            common_s = sorted(step_names_a & step_names_b)
            for sn in added_s:
                job_branch.add(
                    f"  [green]+ step: {sn}[/] ({step_type_label(steps_b[sn])})"
                )
            for sn in removed_s:
                job_branch.add(
                    f"  [red]- step: {sn}[/] ({step_type_label(steps_a[sn])})"
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

    env_rows: list[tuple[str, str, str]] = []
    for key in sorted(set(wf_a.env) | set(wf_b.env)):
        if key not in wf_a.env:
            env_rows.append((key, "[green]+ added[/]", str(wf_b.env[key])[:60]))
        elif key not in wf_b.env:
            env_rows.append((key, "[red]- removed[/]", str(wf_a.env[key])[:60]))
        elif str(wf_a.env[key]) != str(wf_b.env[key]):
            env_rows.append(
                (
                    key,
                    "[yellow]~ changed[/]",
                    f"{str(wf_a.env[key])[:30]} → {str(wf_b.env[key])[:30]}",
                )
            )
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

    tools_a = {k: str(v) for k, v in wf_a.tools.items()}
    tools_b = {k: str(v) for k, v in wf_b.tools.items()}
    tool_rows: list[tuple[str, str, str]] = []
    for key in sorted(set(tools_a) | set(tools_b)):
        if key not in tools_a:
            tool_rows.append((key, "[green]+ added[/]", str(tools_b[key])[:60]))
        elif key not in tools_b:
            tool_rows.append((key, "[red]- removed[/]", str(tools_a[key])[:60]))
        elif str(tools_a[key]) != str(tools_b[key]):
            tool_rows.append(
                (
                    key,
                    "[yellow]~ changed[/]",
                    f"{str(tools_a[key])[:30]} → {str(tools_b[key])[:30]}",
                )
            )
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
