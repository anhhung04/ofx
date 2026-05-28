"""Handler for `ofx flow validate` — workflow validation with diagnostics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ofx.models.workflow import Workflow
from ofx.settings import (
    ALLOWED_WORKFLOW_FILE_EXTENSIONS,
    BUILTIN_WORKFLOWS_DIR,
    DEFAULT_WORKFLOWS_DIRS,
    get_console,
)

logger = logging.getLogger("ofx")


@dataclass
class ValidationResult:
    path: Path
    name: str = ""
    valid: bool = False
    error: str = ""
    jobs: int = 0
    steps: int = 0
    has_dispatch: bool = False
    has_call: bool = False
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    task_refs: list[str] = field(default_factory=list)
    unknown_tasks: list[str] = field(default_factory=list)


def _validate_one(path: Path, check_tasks: bool) -> ValidationResult:
    """Validate a single workflow file and return diagnostics."""
    import yaml

    result = ValidationResult(path=path)

    try:
        data = yaml.safe_load(path.read_text().strip())
        workflow = Workflow.model_validate(data)
        workflow.workflow_path = path
    except Exception as e:
        result.error = str(e)[:200]
        return result

    result.valid = True
    result.name = workflow.name
    result.jobs = len(workflow.jobs)
    result.steps = sum(len(j.steps) for j in workflow.jobs.values())
    result.has_dispatch = workflow.dispatch is not None
    result.has_call = workflow.call is not None
    result.tags = list(workflow.tags)

    # Check for common issues
    for jid, job in workflow.jobs.items():
        needs = (
            job.needs
            if isinstance(job.needs, list)
            else [job.needs]
            if job.needs
            else []
        )
        for dep in needs:
            if dep and dep not in workflow.jobs:
                result.warnings.append(f"Job '{jid}' depends on unknown job '{dep}'")

        if not job.steps:
            result.warnings.append(f"Job '{jid}' has no steps")

        for step in job.steps:
            if step.task:
                result.task_refs.append(step.task)
            elif step.store_creds is not None:
                result.warnings.append(
                    f"Job '{jid}', step '{step.name}': store-creds has no effect "
                    f"on non-task steps (only applies to 'task:' steps)"
                )

    if not result.has_dispatch and not result.has_call:
        result.warnings.append("No dispatch or call trigger defined")

    # Check task references against registry
    if check_tasks and result.task_refs:
        from ofx.tasks.registry import TaskRegistry

        registered = set(TaskRegistry.list_tasks())
        for task_name in set(result.task_refs):
            if task_name not in registered:
                result.unknown_tasks.append(task_name)
                result.warnings.append(f"Task '{task_name}' not found in registry")

    return result


def _print_single_result(result: ValidationResult) -> None:
    """Print detailed validation result for a single workflow."""
    from ofx.commands.ui_helpers import error_exit, print_success

    console = get_console()

    if not result.valid:
        error_exit("Validation Failed", f"[cyan]{result.path}[/]", result.error)

    # Build details
    details: dict[str, str] = {
        "Path": str(result.path),
        "Jobs": str(result.jobs),
        "Steps": str(result.steps),
    }
    if result.tags:
        details["Tags"] = ", ".join(result.tags)

    triggers = []
    if result.has_dispatch:
        triggers.append("dispatch")
    if result.has_call:
        triggers.append("call")
    details["Triggers"] = ", ".join(triggers) if triggers else "direct run"

    if result.task_refs:
        details["Task refs"] = f"{len(set(result.task_refs))} unique"

    print_success(
        "Validation Passed",
        f"[cyan]{result.name}[/] is valid",
        details,
    )

    if result.warnings:
        for w in result.warnings:
            console.print(f"  [yellow]⚠[/] {w}")
        console.print()


def _print_bulk_results(results: list[ValidationResult]) -> None:
    """Print summary table for bulk validation."""
    from rich.table import Table

    console = get_console()

    passed = sum(1 for r in results if r.valid)
    failed = sum(1 for r in results if not r.valid)
    warned = sum(1 for r in results if r.valid and r.warnings)

    table = Table(
        title=f"Workflow Validation: {passed} passed, {failed} failed, {warned} warnings"
    )
    table.add_column("Workflow", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Jobs", justify="right")
    table.add_column("Steps", justify="right")
    table.add_column("Issues", style="dim")

    for r in sorted(results, key=lambda x: (x.valid, x.path)):
        if r.valid:
            status = "[green]✓[/]"
            issues = ""
            if r.warnings:
                status = "[yellow]⚠[/]"
                issues = "; ".join(r.warnings[:2])
                if len(r.warnings) > 2:
                    issues += f" (+{len(r.warnings) - 2} more)"
        else:
            status = "[red]✗[/]"
            issues = r.error[:80]

        name = r.name or r.path.stem
        table.add_row(name, status, str(r.jobs), str(r.steps), issues)

    console.print(table)

    # Print failed details
    failed_results = [r for r in results if not r.valid]
    if failed_results:
        console.print()
        console.print("[bold red]Failed workflows:[/]")
        for r in failed_results:
            console.print(f"  [red]✗[/] {r.path.stem}: {r.error[:120]}")


def _discover_all_workflows() -> list[Path]:
    """Find all workflow files in dedicated workflow directories (not CWD)."""
    from ofx.collections import CollectionManager

    seen: set[str] = set()
    files: list[Path] = []

    # Only scan dedicated workflow directories, not CWD
    dirs: list[Path] = []
    if BUILTIN_WORKFLOWS_DIR.is_dir():
        dirs.append(BUILTIN_WORKFLOWS_DIR)

    user_dir = Path.home() / ".ofx" / "workflows"
    if user_dir.is_dir():
        dirs.append(user_dir)

    # Installed collections
    try:
        manager = CollectionManager()
        for entry in manager.list_installed().values():
            coll_path = Path(entry.path)
            if coll_path.is_dir():
                dirs.append(coll_path)
    except Exception as e:
        logger.debug("Failed to load installed collections for validation: %s", e)

    for d in dirs:
        for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
            for path in sorted(d.rglob(f"*{ext}")):
                resolved = str(path.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(path)

    return files


def validate_workflows(
    workflow_name: str = "",
    all_workflows: bool = False,
    check_tasks: bool = False,
) -> None:
    """Validate one or all workflows with detailed diagnostics."""
    from ofx.commands.ui_helpers import error_exit, print_info, print_warning

    console = get_console()

    if all_workflows:
        files = _discover_all_workflows()
        if not files:
            print_warning(
                "No Workflows", "No workflow files found in search directories."
            )
            return

        print_info("Bulk Validation", f"Validating [cyan]{len(files)}[/] workflows…")
        console.print()

        results = [_validate_one(f, check_tasks=check_tasks) for f in files]
        _print_bulk_results(results)
        return

    if not workflow_name:
        error_exit("Missing Argument", "Provide a workflow name or use --all")

    # Single workflow: try find_workflow first, then recursive search
    from ofx.utils.workflow_utils import find_workflow

    path: Path | None = None
    try:
        wf = find_workflow(workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS))
        path = wf.workflow_path
    except RuntimeError:
        # Recursive fallback
        for d in DEFAULT_WORKFLOWS_DIRS:
            if not d.is_dir():
                continue
            for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
                for match in d.rglob(f"{workflow_name}{ext}"):
                    path = match
                    break
            if path:
                break

    if not path:
        error_exit("Workflow Not Found", f"Could not find workflow '{workflow_name}'")

    print_info("Validating", f"[cyan]{workflow_name}[/]")
    console.print()
    result = _validate_one(path, check_tasks=check_tasks)
    _print_single_result(result)
