"""Handler for `ofx flow info` — display detailed workflow information."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.settings import DEFAULT_WORKFLOWS_DIRS, get_console
from ofx.utils.workflow_utils import find_workflow


def _step_type_label(step) -> str:
    if step.task:
        return f"task: {step.task}"
    if step.uses:
        return f"uses: {step.uses}"
    if step.script:
        return "script"
    if step.script_file:
        return f"script_file: {step.script_file}"
    if step.run:
        lines = step.run.strip().splitlines()
        first = lines[0][:60]
        if len(lines) > 1 or len(lines[0]) > 60:
            first += "…"
        return f"run: {first}"
    return "unknown"


def _build_overview_table(workflow: Workflow) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold white", no_wrap=True)
    table.add_column("Value")

    table.add_row("Name", f"[cyan bold]{workflow.name}[/]")

    desc = workflow.description or "—"
    if desc != "No provided description":
        # Show full description, wrapping naturally
        table.add_row("Description", desc.strip())
    else:
        table.add_row("Description", "[dim]—[/]")

    if workflow.tags:
        table.add_row("Tags", " ".join(f"[cyan]#{t}[/]" for t in workflow.tags))

    table.add_row("Jobs", str(len(workflow.jobs)))
    total_steps = sum(len(j.steps) for j in workflow.jobs.values())
    table.add_row("Steps", str(total_steps))

    if workflow.workflow_path:
        table.add_row("Path", f"[dim]{workflow.workflow_path}[/]")

    has_dispatch = workflow.dispatch is not None
    has_call = workflow.call is not None
    triggers = []
    if has_dispatch:
        triggers.append("dispatch")
    if has_call:
        triggers.append("call")
    table.add_row("Triggers", ", ".join(triggers) if triggers else "[dim]direct run[/]")

    if workflow.tools:
        table.add_row("Tools", ", ".join(sorted(workflow.tools.keys())))

    return table


def _build_inputs_table(workflow: Workflow) -> Table | None:
    if not workflow.dispatch or not workflow.dispatch.inputs:
        return None

    table = Table(title="Inputs", title_style="bold yellow", padding=(0, 1))
    table.add_column("Name", style="cyan bold")
    table.add_column("Type", style="white")
    table.add_column("Required", style="white", justify="center")
    table.add_column("Default", style="dim")
    table.add_column("Alias", style="dim")

    for name, inp in workflow.dispatch.inputs.items():
        req = "✓" if inp.required else ""
        default = str(inp.default) if inp.default is not None else "—"
        alias_val = ", ".join(inp.alias) if isinstance(inp.alias, list) else (inp.alias or "—")
        inp_type = inp.type or "string"
        table.add_row(name, inp_type, req, default, alias_val)

    return table


def _build_jobs_tree(workflow: Workflow, detailed: bool) -> Tree:
    from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()

    tree = Tree("[bold yellow]Execution Plan[/]")

    for stage_idx, stage_jobs in enumerate(schedule.schedule, 1):
        parallel_hint = " [dim](parallel)[/]" if len(stage_jobs) > 1 else ""
        stage_branch = tree.add(f"[bold]Stage {stage_idx}[/]{parallel_hint}")

        for jid in stage_jobs:
            job: Job = workflow.jobs[jid]
            label_parts = [f"[cyan bold]{jid}[/]"]
            if job.name and job.name != jid:
                label_parts.append(f"[dim]({job.name})[/]")

            if job.cloud:
                cloud_label = job.cloud if isinstance(job.cloud, str) else "custom"
                label_parts.append(f"[magenta]☁ {cloud_label}[/]")

            if job.strategy and job.strategy.matrix:
                keys = list(job.strategy.matrix.keys())
                label_parts.append(f"[yellow]⊞ matrix({', '.join(keys)})[/]")

            if job.needs:
                needs = job.needs if isinstance(job.needs, list) else [job.needs]
                if needs:
                    label_parts.append(f"[dim]← {', '.join(needs)}[/]")

            job_branch = stage_branch.add(" ".join(label_parts))

            if detailed:
                for step in job.steps:
                    step_label = f"[white]{step.name}[/] [dim]{_step_type_label(step)}[/]"
                    if step.timeout and step.timeout != 1440:
                        step_label += f" [dim]⏱{step.timeout}m[/]"
                    job_branch.add(step_label)

                if job.outputs:
                    out_branch = job_branch.add("[dim italic]outputs:[/]")
                    for k in job.outputs:
                        out_branch.add(f"[dim]{k}[/]")

    return tree


def _build_outputs_table(workflow: Workflow) -> Table | None:
    jobs_with_outputs = {jid: job for jid, job in workflow.jobs.items() if job.outputs}
    if not jobs_with_outputs:
        return None

    table = Table(title="Job Outputs", title_style="bold yellow", padding=(0, 1))
    table.add_column("Job", style="cyan")
    table.add_column("Output", style="white")
    table.add_column("Source", style="dim", max_width=60)

    for jid, job in jobs_with_outputs.items():
        first = True
        for key, val in job.outputs.items():
            table.add_row(jid if first else "", key, str(val)[:60])
            first = False

    return table


def _find_workflow_fuzzy(name: str) -> Workflow:
    """Find workflow by name, with recursive fallback for bare names."""
    dirs = tuple(DEFAULT_WORKFLOWS_DIRS)
    try:
        return find_workflow(name, dirs)
    except RuntimeError:
        pass
    # Fallback: search recursively for <name>.yml in all search dirs
    from ofx.settings import ALLOWED_WORKFLOW_FILE_EXTENSIONS

    for d in DEFAULT_WORKFLOWS_DIRS:
        if not d.is_dir():
            continue
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for match in d.rglob(f"{name}{ext}"):
                import yaml

                data = yaml.safe_load(match.read_text().strip())
                wf = Workflow.model_validate(data)
                wf.workflow_path = match
                return wf
    raise RuntimeError(f"Could not find workflow '{name}'")


def show_info(workflow_name: str, detailed: bool = False) -> None:
    """Display detailed information about a workflow."""
    console = get_console()

    try:
        workflow = _find_workflow_fuzzy(workflow_name)
    except Exception as e:
        from ofx.commands.ui_helpers import print_error

        print_error("Workflow Not Found", f"Could not find workflow '{workflow_name}'", str(e))
        return

    # Overview
    overview = _build_overview_table(workflow)
    console.print(Panel(overview, title=f"[bold]📋 {workflow.name}[/]", border_style="cyan", padding=(1, 2)))

    # Inputs
    inputs_table = _build_inputs_table(workflow)
    if inputs_table:
        console.print(inputs_table)
        console.print()

    # Execution plan
    jobs_tree = _build_jobs_tree(workflow, detailed=detailed)
    console.print(jobs_tree)
    console.print()

    # Outputs
    outputs_table = _build_outputs_table(workflow)
    if outputs_table:
        console.print(outputs_table)
