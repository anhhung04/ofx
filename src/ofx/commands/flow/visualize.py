"""Handler for `ofx flow visualize` — workflow DAG visualization."""

from __future__ import annotations

import json
from typing import Any

from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.settings import DEFAULT_WORKFLOWS_DIRS, get_console
from ofx.utils.workflow_utils import find_workflow


def _find_workflow_fuzzy(name: str) -> Workflow:
    """Find workflow by name, with recursive fallback for bare names."""
    dirs = tuple(DEFAULT_WORKFLOWS_DIRS)
    try:
        return find_workflow(name, dirs)
    except RuntimeError:
        pass
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


def _build_dag_data(workflow: Workflow) -> dict[str, Any]:
    """Build a serialisable DAG structure from a workflow."""
    from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()

    jobs_data: dict[str, dict[str, Any]] = {}
    for jid, job in workflow.jobs.items():
        jobs_data[jid] = {
            "name": job.name or jid,
            "needs": job.needs if isinstance(job.needs, list) else [job.needs] if job.needs else [],
            "steps": len(job.steps),
            "cloud": bool(job.cloud),
            "matrix": bool(job.strategy and job.strategy.matrix),
            "outputs": list(job.outputs.keys()) if job.outputs else [],
        }

    return {
        "name": workflow.name,
        "stages": schedule.schedule,
        "jobs": jobs_data,
        "dependencies": [
            {"from": dep, "to": jid}
            for jid, job in workflow.jobs.items()
            for dep in (job.needs if isinstance(job.needs, list) else [job.needs] if job.needs else [])
            if dep
        ],
    }


def _render_terminal(workflow: Workflow, detailed: bool) -> None:
    """Render a rich terminal DAG visualization."""
    from rich.panel import Panel
    from rich.table import Table

    from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

    console = get_console()
    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()
    stages = schedule.schedule

    # Stats row
    total_jobs = len(workflow.jobs)
    total_steps = sum(len(j.steps) for j in workflow.jobs.values())
    total_stages = len(stages)
    max_parallel = max(len(s) for s in stages) if stages else 0
    deps_count = sum(
        len(j.needs) if isinstance(j.needs, list) else (1 if j.needs else 0)
        for j in workflow.jobs.values()
    )
    cloud_count = sum(1 for j in workflow.jobs.values() if j.cloud)

    stats = Table(show_header=False, box=None, padding=(0, 2))
    stats.add_column("", style="bold")
    stats.add_column("")
    stats.add_row("Jobs", f"[cyan]{total_jobs}[/]")
    stats.add_row("Steps", f"[cyan]{total_steps}[/]")
    stats.add_row("Stages", f"[cyan]{total_stages}[/]")
    stats.add_row("Max parallel", f"[cyan]{max_parallel}[/]")
    stats.add_row("Dependencies", f"[cyan]{deps_count}[/]")
    if cloud_count:
        stats.add_row("Cloud jobs", f"[magenta]{cloud_count}[/]")

    console.print(
        Panel(
            stats,
            title=f"[bold]📊 {workflow.name}[/]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    # DAG rendering — stage by stage
    BOX_MIN_W = 24
    CONNECTOR = "│"

    for stage_idx, stage_jobs in enumerate(stages):
        # Stage header
        if len(stage_jobs) > 1:
            console.print(f"  [bold yellow]━━ Stage {stage_idx + 1} (parallel) ━━[/]")
        else:
            console.print(f"  [bold yellow]━━ Stage {stage_idx + 1} ━━[/]")

        # Render job boxes for this stage
        for jid in stage_jobs:
            job: Job = workflow.jobs[jid]
            needs = job.needs if isinstance(job.needs, list) else [job.needs] if job.needs else []

            # Build box content
            box_lines: list[str] = []
            name_line = jid
            if job.name and job.name != jid:
                name_line = f"{jid} ({job.name})"

            badges: list[str] = []
            if job.cloud:
                cloud_label = job.cloud if isinstance(job.cloud, str) else "custom"
                badges.append(f"☁ {cloud_label}")
            if job.strategy and job.strategy.matrix:
                keys = list(job.strategy.matrix.keys())
                badges.append(f"⊞ matrix({','.join(keys)})")

            box_lines.append(name_line)
            if badges:
                box_lines.append("  ".join(badges))
            box_lines.append(f"{len(job.steps)} steps")

            if needs:
                box_lines.append(f"← {', '.join(needs)}")

            if detailed:
                for step in job.steps:
                    kind = "task" if step.task else "uses" if step.uses else "run" if step.run else "script"
                    box_lines.append(f"  • {step.name} [{kind}]")
                if job.outputs:
                    box_lines.append(f"  ↳ outputs: {', '.join(job.outputs.keys())}")

            # Render box
            width = max(len(line) for line in box_lines) + 4
            width = max(width, BOX_MIN_W)

            console.print(f"    ┌{'─' * width}┐")
            for line in box_lines:
                padded = line.ljust(width - 2)
                console.print(f"    │ {padded} │")
            console.print(f"    └{'─' * width}┘")

        # Connector between stages
        if stage_idx < len(stages) - 1:
            console.print(f"    {CONNECTOR}")
            console.print("    ▼")

    console.print()


def _render_dot(workflow: Workflow) -> str:
    """Generate GraphViz DOT format."""
    from ofx.runner.execution.workflow_scheduler import WorkflowScheduler

    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()

    lines = [
        f'digraph "{workflow.name}" {{',
        "  rankdir=TB;",
        '  node [shape=box, style="rounded,filled", fillcolor="#e8f4fd", fontname="Helvetica"];',
        '  edge [color="#666666"];',
        "",
    ]

    # Subgraphs for stages
    for stage_idx, stage_jobs in enumerate(schedule.schedule):
        lines.append(f"  subgraph cluster_stage{stage_idx} {{")
        lines.append(f'    label="Stage {stage_idx + 1}";')
        lines.append('    style=dashed; color="#cccccc";')
        for jid in stage_jobs:
            job = workflow.jobs[jid]
            label = jid
            if job.cloud:
                label += "\\n☁ cloud"
            if job.strategy and job.strategy.matrix:
                label += "\\n⊞ matrix"
            label += f"\\n({len(job.steps)} steps)"
            lines.append(f'    "{jid}" [label="{label}"];')
        lines.append("  }")
        lines.append("")

    # Edges
    for jid, job in workflow.jobs.items():
        needs = job.needs if isinstance(job.needs, list) else [job.needs] if job.needs else []
        for dep in needs:
            if dep:
                lines.append(f'  "{dep}" -> "{jid}";')

    lines.append("}")
    return "\n".join(lines)


def _render_json(workflow: Workflow) -> str:
    """Generate JSON representation of the DAG."""
    return json.dumps(_build_dag_data(workflow), indent=2)


def visualize(
    workflow_name: str,
    format: str = "terminal",
    output: str = "",
    detailed: bool = False,
) -> None:
    """Visualize workflow dependencies and execution flow."""
    console = get_console()

    try:
        workflow = _find_workflow_fuzzy(workflow_name)
    except Exception as e:
        from ofx.commands.ui_helpers import print_error

        print_error("Workflow Not Found", f"Could not find workflow '{workflow_name}'", str(e))
        return

    if format == "terminal":
        _render_terminal(workflow, detailed=detailed)
        return

    if format == "dot":
        content = _render_dot(workflow)
    elif format == "json":
        content = _render_json(workflow)
    else:
        from ofx.commands.ui_helpers import print_error

        print_error("Invalid Format", f"Unknown format: '{format}'", "Supported: terminal, dot, json")
        return

    if output:
        from pathlib import Path

        Path(output).write_text(content)
        from ofx.commands.ui_helpers import print_success

        print_success("Visualization Saved", f"Written to {output}")
    else:
        console.print(content, highlight=False, markup=False)
