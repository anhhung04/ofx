"""Handler for `ofx flow info` — display detailed workflow information."""

from __future__ import annotations

from contextlib import suppress

from rich.panel import Panel

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.runner.step_descriptors import step_type_label
from ofx.settings import DEFAULT_WORKFLOWS_DIRS, get_console
from ofx.utils.workflow_utils import find_workflow

def _find_workflow_fuzzy(name: str) -> Workflow:
    """Find workflow by name, with recursive fallback for bare names."""
    dirs = tuple(DEFAULT_WORKFLOWS_DIRS)
    with suppress(RuntimeError):
        return find_workflow(name, dirs)
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
    from rich.table import Table
    from rich.tree import Tree
    from ofx.runner.workflow_scheduler import WorkflowScheduler

    console = get_console()

    try:
        workflow = _find_workflow_fuzzy(workflow_name)
    except Exception as e:
        from ofx.commands.ui_helpers import error_exit

        error_exit(
            "Workflow Not Found", f"Could not find workflow '{workflow_name}'", str(e)
        )

    overview = Table(show_header=False, box=None, padding=(0, 2))
    overview.add_column("Key", style="bold white", no_wrap=True)
    overview.add_column("Value")

    overview.add_row("Name", f"[cyan bold]{workflow.name}[/]")

    desc = workflow.description or "—"
    if desc != "No provided description":
        overview.add_row("Description", desc.strip())
    else:
        overview.add_row("Description", "[dim]—[/]")

    if workflow.tags:
        overview.add_row("Tags", " ".join(f"[cyan]#{tag}[/]" for tag in workflow.tags))

    overview.add_row("Jobs", str(len(workflow.jobs)))
    total_steps = sum(len(job.steps) for job in workflow.jobs.values())
    overview.add_row("Steps", str(total_steps))

    if workflow.workflow_path:
        overview.add_row("Path", f"[dim]{workflow.workflow_path}[/]")

    triggers = []
    if workflow.dispatch is not None:
        triggers.append("dispatch")
    if workflow.call is not None:
        triggers.append("call")
    overview.add_row("Triggers", ", ".join(triggers) if triggers else "[dim]direct run[/]")

    if workflow.tools:
        overview.add_row("Tools", ", ".join(sorted(workflow.tools.keys())))

    console.print(
        Panel(
            overview,
            title=f"[bold]📋 {workflow.name}[/]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    if workflow.dispatch and workflow.dispatch.inputs:
        inputs_table = Table(title="Inputs", title_style="bold yellow", padding=(0, 1))
        inputs_table.add_column("Name", style="cyan bold")
        inputs_table.add_column("Type", style="white")
        inputs_table.add_column("Required", style="white", justify="center")
        inputs_table.add_column("Default", style="dim")
        inputs_table.add_column("Alias", style="dim")

        for name, input_spec in workflow.dispatch.inputs.items():
            req = "✓" if input_spec.required else ""
            default = str(input_spec.default) if input_spec.default is not None else "—"
            alias_value = (
                ", ".join(input_spec.alias)
                if isinstance(input_spec.alias, list)
                else (input_spec.alias or "—")
            )
            input_type = input_spec.type or "string"
            inputs_table.add_row(name, input_type, req, default, alias_value)

        console.print(inputs_table)
        console.print()

    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()
    jobs_tree = Tree("[bold yellow]Execution Plan[/]")

    for stage_idx, stage_jobs in enumerate(schedule.schedule, 1):
        parallel_hint = " [dim](parallel)[/]" if len(stage_jobs) > 1 else ""
        stage_branch = jobs_tree.add(f"[bold]Stage {stage_idx}[/]{parallel_hint}")

        for job_id in stage_jobs:
            job: Job = workflow.jobs[job_id]
            label_parts = [f"[cyan bold]{job_id}[/]"]
            if job.name and job.name != job_id:
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
                    step_label = f"[white]{step.name}[/] [dim]{step_type_label(step)}[/]"
                    if step.timeout and step.timeout != 1440:
                        step_label += f" [dim]⏱{step.timeout}m[/]"
                    job_branch.add(step_label)

                if job.outputs:
                    out_branch = job_branch.add("[dim italic]outputs:[/]")
                    for key in job.outputs:
                        out_branch.add(f"[dim]{key}[/]")

    console.print(jobs_tree)
    console.print()

    jobs_with_outputs = {job_id: job for job_id, job in workflow.jobs.items() if job.outputs}
    if jobs_with_outputs:
        outputs_table = Table(title="Job Outputs", title_style="bold yellow", padding=(0, 1))
        outputs_table.add_column("Job", style="cyan")
        outputs_table.add_column("Output", style="white")
        outputs_table.add_column("Source", style="dim", max_width=60)

        for job_id, job in jobs_with_outputs.items():
            first = True
            for key, value in job.outputs.items():
                outputs_table.add_row(job_id if first else "", key, str(value)[:60])
                first = False

        console.print(outputs_table)
