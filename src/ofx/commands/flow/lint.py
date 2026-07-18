"""Handler for `ofx flow lint` — best-practice checks for workflows."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from ofx.settings import (
    ALLOWED_WORKFLOW_FILE_EXTENSIONS,
    BUILTIN_WORKFLOWS_DIR,
    DEFAULT_WORKFLOWS_DIRS,
    get_console,
)

logger = logging.getLogger("ofx")

CollectionManager = None
find_workflow = None

@dataclass
class LintIssue:
    severity: str
    message: str
    location: str = ""

@dataclass
class LintResult:
    path: Path
    name: str = ""
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warn")

def _lint_workflow(path: Path) -> LintResult:
    """Run best-practice checks on a single workflow file."""
    import yaml

    from ofx.models.workflow import Workflow

    result = LintResult(path=path)

    try:
        data = yaml.safe_load(path.read_text().strip())
        workflow = Workflow.model_validate(data)
    except Exception as e:
        result.issues.append(LintIssue("error", f"Invalid YAML/schema: {str(e)[:120]}"))
        return result

    result.name = workflow.name

    if not workflow.description or workflow.description == "No provided description":
        result.issues.append(LintIssue("warn", "Missing or default description"))

    if not workflow.tags:
        result.issues.append(LintIssue("warn", "No tags defined"))

    if not workflow.dispatch and not workflow.call:
        result.issues.append(
            LintIssue("info", "No dispatch or call trigger — can only run directly")
        )

    if workflow.dispatch and not workflow.dispatch.inputs:
        result.issues.append(
            LintIssue("info", "Dispatch defined but no inputs declared")
        )

    for jid, job in workflow.jobs.items():
        if not job.name:
            result.issues.append(LintIssue("warn", "Job has no name", location=jid))

        if not job.outputs:
            result.issues.append(
                LintIssue("info", "Job has no outputs declared", location=jid)
            )

        for step in job.steps:
            if not step.name or step.name.startswith("<should_be_replaced>"):
                result.issues.append(
                    LintIssue(
                        "warn",
                        "Step has no name",
                        location=f"{jid}.step[{step.step_index}]",
                    )
                )

            if step.task and step.timeout == 1440:
                result.issues.append(
                    LintIssue(
                        "info",
                        f"Task step '{step.name}' uses default 24h timeout",
                        location=jid,
                    )
                )

            if step.run and len(step.run) > 500:
                result.issues.append(
                    LintIssue(
                        "info",
                        f"Step '{step.name}' has a long run command ({len(step.run)} chars) — consider script",
                        location=jid,
                    )
                )

    return result
def lint_workflows(all_workflows: bool = False, workflow_name: str = "") -> None:
    """Run best-practice lint checks on workflows."""
    from rich.table import Table

    from ofx.commands.ui_helpers import error_exit, print_info, print_warning

    console = get_console()

    if all_workflows:
        seen: set[str] = set()
        files: list[Path] = []

        dirs: list[Path] = []
        if BUILTIN_WORKFLOWS_DIR.is_dir():
            dirs.append(BUILTIN_WORKFLOWS_DIR)
        user_dir = Path.home() / ".ofx" / "workflows"
        if user_dir.is_dir():
            dirs.append(user_dir)

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
            logger.debug("Failed to load installed collections for linting: %s", e)

        for directory in dirs:
            for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
                for path in sorted(directory.rglob(f"*{ext}")):
                    if path.name in ("collection.yaml", "collection.yml"):
                        continue
                    resolved = str(path.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(path)
    elif workflow_name:
        files: list[Path] = []
        workflow_finder = find_workflow
        if workflow_finder is None:
            from ofx.utils.workflow_utils import find_workflow as workflow_finder

        with suppress(RuntimeError):
            wf = workflow_finder(workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS))
            if wf.workflow_path:
                files = [wf.workflow_path]

        if not files:
            for directory in DEFAULT_WORKFLOWS_DIRS:
                if not directory.is_dir():
                    continue
                for ext in ALLOWED_WORKFLOW_FILE_EXTENSIONS:
                    for match in directory.rglob(f"{workflow_name}{ext}"):
                        files = [match]
                        break
                    if files:
                        break
                if files:
                    break
    else:
        error_exit("Missing Argument", "Provide a workflow name or use --all")

    if not files:
        print_warning("No Workflows", "No workflow files found.")
        return

    results = [_lint_workflow(f) for f in files]

    total_errors = sum(r.error_count for r in results)
    total_warns = sum(r.warn_count for r in results)
    total_infos = sum(sum(1 for i in r.issues if i.severity == "info") for r in results)
    clean = sum(1 for r in results if not r.issues)

    if all_workflows:
        results_with_issues = [r for r in results if r.issues]
        print_info(
            "Lint Results",
            f"{len(results)} workflows: {clean} clean, {total_warns} warnings, {total_errors} errors, {total_infos} info",
        )
        console.print()

        if not results_with_issues:
            console.print("[green]All workflows pass lint checks![/]")
            return

        table = Table(title="Lint Issues", padding=(0, 1))
        table.add_column("Workflow", style="cyan")
        table.add_column("", justify="center", width=3)
        table.add_column("Issue")
        table.add_column("Location", style="dim")

        for r in sorted(
            results_with_issues, key=lambda x: (-x.error_count, -x.warn_count, x.name)
        ):
            first = True
            for issue in r.issues:
                table.add_row(
                    r.name if first else "",
                    {"error": "[red]✗[/]", "warn": "[yellow]⚠[/]", "info": "[dim]ℹ[/]"}.get(issue.severity, "?"),
                    issue.message,
                    issue.location,
                )
                first = False

        console.print(table)
    else:
        r = results[0]
        if not r.issues:
            from ofx.commands.ui_helpers import print_success

            print_success(
                "Lint Passed", f"[cyan]{r.name or r.path.stem}[/] — no issues found"
            )
            return

        console.print(f"[bold]{r.name or r.path.stem}[/]  ({r.path})")
        console.print()
        for issue in r.issues:
            loc = f" [dim]({issue.location})[/]" if issue.location else ""
            severity_icon = {"error": "[red]✗[/]", "warn": "[yellow]⚠[/]", "info": "[dim]ℹ[/]"}.get(issue.severity, "?")
            console.print(f"  {severity_icon} {issue.message}{loc}")
        console.print()
        console.print(
            f"  {r.error_count} errors, {r.warn_count} warnings, {sum(1 for i in r.issues if i.severity == 'info')} info"
        )
