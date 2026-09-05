"""Handler for `ofx flow validate` — workflow validation with diagnostics."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ofx.models.workflow import Workflow
from ofx.settings import (
    ALLOWED_WORKFLOW_FILE_EXTENSIONS,
    BUILTIN_WORKFLOWS_DIR,  # noqa: F401 - compatibility for callers/tests monkeypatching this module
    get_console,
    get_workflow_search_dirs,
)

logger = logging.getLogger("ofx")

CollectionManager = None
find_workflow = None

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
            pass  # Step validation is handled by the Step model

    if not result.has_dispatch and not result.has_call:
        result.warnings.append("No dispatch or call trigger defined")

    if check_tasks and result.task_refs:
        result.warnings.append(
            "Task validation is no longer supported (task system removed). "
            "Use 'script:' or 'run:' steps instead."
        )

    return result
def validate_workflows(
    workflow_name: str = "",
    all_workflows: bool = False,
    check_tasks: bool = False,
) -> None:
    """Validate one or all workflows with detailed diagnostics."""
    from ofx.commands.ui_helpers import error_exit, print_info, print_warning
    from rich.table import Table

    console = get_console()

    if all_workflows:
        seen: set[str] = set()
        files: list[Path] = []
        dirs = get_workflow_search_dirs()

        collection_manager_cls = CollectionManager
        if collection_manager_cls is None:
            from ofx.collections import CollectionManager as collection_manager_cls

        try:
            manager = collection_manager_cls()
            for entry in manager.list_installed().values():
                coll_path = Path(entry.path)
                if coll_path.is_dir():
                    dirs.append(coll_path)
        except Exception as e:
            logger.debug("Failed to load installed collections for validation: %s", e)

        for directory in dirs:
            for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
                for path in sorted(directory.rglob(f"*{ext}")):
                    # Skip collection manifest files (they lack a `jobs` section)
                    if path.name in ("collection.yaml", "collection.yml"):
                        continue
                    resolved = str(path.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(path)

        if not files:
            print_warning(
                "No Workflows", "No workflow files found in search directories."
            )
            return

        print_info("Bulk Validation", f"Validating [cyan]{len(files)}[/] workflows…")
        console.print()

        results = [_validate_one(f, check_tasks=check_tasks) for f in files]
        passed = sum(1 for result in results if result.valid)
        failed = sum(1 for result in results if not result.valid)
        warned = sum(1 for result in results if result.valid and result.warnings)

        table = Table(
            title=(
                f"Workflow Validation: {passed} passed, {failed} failed, {warned} warnings"
            )
        )
        table.add_column("Workflow", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Jobs", justify="right")
        table.add_column("Steps", justify="right")
        table.add_column("Issues", style="dim")

        for result in sorted(results, key=lambda item: (item.valid, item.path)):
            if result.valid:
                status = "[green]✓[/]"
                issues = ""
                if result.warnings:
                    status = "[yellow]⚠[/]"
                    issues = "; ".join(result.warnings[:2])
                    if len(result.warnings) > 2:
                        issues += f" (+{len(result.warnings) - 2} more)"
            else:
                status = "[red]✗[/]"
                issues = result.error[:80]

            name = result.name or result.path.stem
            table.add_row(name, status, str(result.jobs), str(result.steps), issues)

        console.print(table)

        failed_results = [result for result in results if not result.valid]
        if failed_results:
            console.print()
            console.print("[bold red]Failed workflows:[/]")
            for result in failed_results:
                console.print(
                    f"  [red]✗[/] {result.path.stem}: {result.error[:120]}"
                )
        return

    if not workflow_name:
        error_exit("Missing Argument", "Provide a workflow name or use --all")

    path: Path | None = None
    workflow_finder = find_workflow
    if workflow_finder is None:
        from ofx.utils.workflow_utils import find_workflow as workflow_finder

    try:
        wf = workflow_finder(workflow_name, tuple(get_workflow_search_dirs()))
        path = wf.workflow_path
    except RuntimeError:
        for d in get_workflow_search_dirs():
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
    if not result.valid:
        error_exit("Validation Failed", f"[cyan]{result.path}[/]", result.error)

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

    from ofx.commands.ui_helpers import print_success

    print_success(
        "Validation Passed",
        f"[cyan]{result.name}[/] is valid",
        details,
    )

    if result.warnings:
        for warning in result.warnings:
            console.print(f"  [yellow]⚠[/] {warning}")
        console.print()
