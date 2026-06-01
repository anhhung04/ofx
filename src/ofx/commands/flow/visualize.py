"""Handler for `ofx flow visualize` — workflow DAG visualization."""

from __future__ import annotations

import json

from ofx.commands.flow.info import _find_workflow_fuzzy
from ofx.models.job import Job
from ofx.models.workflow import Workflow
from ofx.settings import get_console


def visualize(
    workflow_name: str,
    format: str = "terminal",
    output: str = "",
    detailed: bool = False,
) -> None:
    """Visualize workflow dependencies and execution flow."""
    from rich.panel import Panel
    from rich.table import Table
    from ofx.runner.workflow_scheduler import WorkflowScheduler

    console = get_console()

    try:
        workflow = _find_workflow_fuzzy(workflow_name)
    except Exception as e:
        from ofx.commands.ui_helpers import error_exit

        error_exit(
            "Workflow Not Found", f"Could not find workflow '{workflow_name}'", str(e)
        )

    scheduler = WorkflowScheduler(jobs=workflow.jobs)
    schedule = scheduler.plan()

    if format == "terminal":
        stages = schedule.schedule
        total_jobs = len(workflow.jobs)
        total_steps = sum(len(job.steps) for job in workflow.jobs.values())
        total_stages = len(stages)
        max_parallel = max(len(stage) for stage in stages) if stages else 0
        deps_count = sum(
            len(job.needs) if isinstance(job.needs, list) else (1 if job.needs else 0)
            for job in workflow.jobs.values()
        )
        cloud_count = sum(1 for job in workflow.jobs.values() if job.cloud)

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

        box_min_width = 24
        connector = "│"

        for stage_idx, stage_jobs in enumerate(stages):
            if len(stage_jobs) > 1:
                console.print(f"  [bold yellow]━━ Stage {stage_idx + 1} (parallel) ━━[/]")
            else:
                console.print(f"  [bold yellow]━━ Stage {stage_idx + 1} ━━[/]")

            for job_id in stage_jobs:
                job: Job = workflow.jobs[job_id]
                needs = (
                    job.needs
                    if isinstance(job.needs, list)
                    else [job.needs]
                    if job.needs
                    else []
                )

                box_lines: list[str] = []
                name_line = job_id
                if job.name and job.name != job_id:
                    name_line = f"{job_id} ({job.name})"

                badges: list[str] = []
                if job.cloud:
                    cloud_label = job.cloud if isinstance(job.cloud, str) else "custom"
                    badges.append(f"☁ {cloud_label}")
                if job.strategy and job.strategy.matrix:
                    keys = list(job.strategy.matrix.keys())
                    badges.append(f"⊞ matrix({','.join(keys)})")
                has_pipe = any(step.pipe is not None for step in job.steps)
                if has_pipe:
                    badges.append("🔗 pipe")

                box_lines.append(name_line)
                if badges:
                    box_lines.append("  ".join(badges))
                box_lines.append(f"{len(job.steps)} steps")

                if needs:
                    box_lines.append(f"← {', '.join(needs)}")

                if detailed:
                    for step in job.steps:
                        kind = (
                            "pipe"
                            if step.pipe
                            else "task"
                            if step.task
                            else "uses"
                            if step.uses
                            else "run"
                            if step.run
                            else "script"
                        )
                        box_lines.append(f"  • {step.name} [{kind}]")
                    if job.outputs:
                        box_lines.append(f"  ↳ outputs: {', '.join(job.outputs.keys())}")

                width = max(len(line) for line in box_lines) + 4
                width = max(width, box_min_width)

                console.print(f"    ┌{'─' * width}┐")
                for line in box_lines:
                    padded = line.ljust(width - 2)
                    console.print(f"    │ {padded} │")
                console.print(f"    └{'─' * width}┘")

            if stage_idx < len(stages) - 1:
                console.print(f"    {connector}")
                console.print("    ▼")

        console.print()
        return

    if format == "dot":
        lines = [
            f'digraph "{workflow.name}" {{',
            "  rankdir=TB;",
            '  node [shape=box, style="rounded,filled", fillcolor="#e8f4fd", fontname="Helvetica"];',
            '  edge [color="#666666"];',
            "",
        ]

        for stage_idx, stage_jobs in enumerate(schedule.schedule):
            lines.append(f"  subgraph cluster_stage{stage_idx} {{")
            lines.append(f'    label="Stage {stage_idx + 1}";')
            lines.append('    style=dashed; color="#cccccc";')
            for job_id in stage_jobs:
                job = workflow.jobs[job_id]
                label = job_id
                if job.cloud:
                    label += "\\n☁ cloud"
                if job.strategy and job.strategy.matrix:
                    label += "\\n⊞ matrix"
                if any(step.pipe is not None for step in job.steps):
                    label += "\\n🔗 pipe"
                label += f"\\n({len(job.steps)} steps)"
                lines.append(f'    "{job_id}" [label="{label}"];')
            lines.append("  }")
            lines.append("")

        for job_id, job in workflow.jobs.items():
            needs = (
                job.needs
                if isinstance(job.needs, list)
                else [job.needs]
                if job.needs
                else []
            )
            for dep in needs:
                if dep:
                    lines.append(f'  "{dep}" -> "{job_id}";')

        lines.append("}")
        content = "\n".join(lines)
    elif format == "json":
        jobs_data: dict[str, dict[str, object]] = {}
        for job_id, job in workflow.jobs.items():
            jobs_data[job_id] = {
                "name": job.name or job_id,
                "needs": job.needs
                if isinstance(job.needs, list)
                else [job.needs]
                if job.needs
                else [],
                "steps": len(job.steps),
                "cloud": bool(job.cloud),
                "matrix": bool(job.strategy and job.strategy.matrix),
                "pipe": any(step.pipe is not None for step in job.steps),
                "outputs": list(job.outputs.keys()) if job.outputs else [],
            }

        content = json.dumps(
            {
                "name": workflow.name,
                "stages": schedule.schedule,
                "jobs": jobs_data,
                "dependencies": [
                    {"from": dep, "to": job_id}
                    for job_id, job in workflow.jobs.items()
                    for dep in (
                        job.needs
                        if isinstance(job.needs, list)
                        else [job.needs]
                        if job.needs
                        else []
                    )
                    if dep
                ],
            },
            indent=2,
        )
    else:
        from ofx.commands.ui_helpers import error_exit

        error_exit(
            "Invalid Format",
            f"Unknown format: '{format}'",
            "Supported: terminal, dot, json",
        )

    if output:
        from pathlib import Path

        Path(output).write_text(content)
        from ofx.commands.ui_helpers import print_success

        print_success("Visualization Saved", f"Written to {output}")
    else:
        console.print(content, highlight=False, markup=False)
