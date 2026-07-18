import logging
import shutil
from pathlib import Path

from ofx.commands.ui_helpers import print_info, print_warning
from ofx.runner import RunContext
from ofx.runner.tool_installer import ToolInstallerRunner
from ofx.settings import TOOLS_BIN_DIR, get_workflow_search_dirs, settings

logger = logging.getLogger(settings.app_branding)

class ToolsInstallHandler:
    def __init__(
        self,
        workflow_name: str = "",
        all_workflows: bool = False,
    ):
        self.workflow_name = workflow_name
        self.all_workflows = all_workflows

    async def run(self):
        """Install tools from workflow configurations"""
        from ofx.utils.workflow_utils import find_all_workflows, find_workflow

        if not self.workflow_name and not self.all_workflows:
            print_warning(
                "Missing Input",
                "Please specify either a workflow name or use --all.",
            )
            return

        workflows_to_process = []

        if self.all_workflows:
            search_dirs = get_workflow_search_dirs()
            workflows_to_process = find_all_workflows(search_dirs)
            if not workflows_to_process:
                print_warning("No Workflows", "No workflow files found.")
                return
        elif self.workflow_name:
            try:
                workflow = find_workflow(
                    self.workflow_name, tuple(get_workflow_search_dirs())
                )
                workflows_to_process = [workflow.workflow_path]
            except RuntimeError:
                print_warning(
                    "Workflow Not Found",
                    f"Could not find workflow '{self.workflow_name}'",
                )
                return

        all_tools = self._collect_tools_from_workflows(workflows_to_process)

        if not all_tools:
            print_warning(
                "No Tools",
                "No tools configured in the specified workflow(s).",
            )
            return

        self._display_tools_table(all_tools)

        installer = ToolInstallerRunner(
            tools=all_tools,
            ctx=RunContext(),
            parent=None,
        )

        await self._install_tools(installer)

    def _collect_tools_from_workflows(
        self, workflow_paths: list[Path]
    ) -> dict[str, str]:
        """Collect all unique tools from workflows, recursively resolving subworkflows."""
        all_tools: dict[str, str] = {}
        visited: set[Path] = set()

        for workflow_path in workflow_paths:
            self._collect_tools_recursive(workflow_path, all_tools, visited)

        return all_tools

    def _collect_tools_recursive(
        self,
        workflow_path: Path,
        all_tools: dict[str, str],
        visited: set[Path],
    ) -> None:
        """Recursively collect tools from a workflow and its subworkflows."""
        import yaml

        from ofx.models.workflow import Workflow
        from ofx.tasks.registry import TaskRegistry
        from ofx.utils.workflow_utils import find_workflow

        resolved = workflow_path.resolve()
        if resolved in visited:
            return
        visited.add(resolved)

        try:
            with open(workflow_path) as f:
                workflow_data = yaml.safe_load(f)

            workflow = Workflow.model_validate(workflow_data)

            if workflow.tools:
                for tool_bin, tool_val in workflow.tools.items():
                    if isinstance(tool_val, str):
                        all_tools[tool_bin] = tool_val
                    elif hasattr(tool_val, "install"):
                        all_tools[tool_bin] = tool_val.install
                    elif isinstance(tool_val, dict):
                        all_tools[tool_bin] = tool_val.get("install", "")

            search_dirs = list(get_workflow_search_dirs())
            parent_dir = workflow_path.parent.resolve()
            if parent_dir not in search_dirs:
                search_dirs.insert(0, parent_dir)

            for job in workflow.jobs.values():
                for step in job.steps:
                    if step.task:
                        task_cls = TaskRegistry.get(step.task)
                        if task_cls and task_cls.install_cmd and task_cls.cmd:
                            all_tools[task_cls.cmd] = task_cls.install_cmd

                    if step.uses:
                        try:
                            sub_wf = find_workflow(step.uses, tuple(search_dirs))
                            if sub_wf.workflow_path:
                                self._collect_tools_recursive(
                                    sub_wf.workflow_path, all_tools, visited
                                )
                        except Exception as e:
                            logger.debug(
                                f"Could not resolve subworkflow '{step.uses}': {e}"
                            )

            if all_tools:
                logger.debug(
                    f"Found {len(all_tools)} tools in workflow: {workflow_path.name}"
                )
        except Exception as e:
            logger.error(f"Error loading workflow {workflow_path}: {e}")
            from ofx.settings import get_console

            console = get_console()
            console.print(
                f"[yellow]Warning: Could not load {workflow_path.name}: {e}[/yellow]"
            )

    def _display_tools_table(self, tools: dict[str, str]):
        """Display tools in a formatted table"""
        from rich.table import Table

        from ofx.settings import get_console

        console = get_console()

        table = Table(
            title="Tools to Install", show_header=True, header_style="bold cyan"
        )
        table.add_column("Tool", style="green")
        table.add_column("Install Command", style="yellow")
        table.add_column("Status", style="blue")

        for tool_bin, install_cmd in tools.items():
            tool_path = TOOLS_BIN_DIR / tool_bin
            tool_exists = tool_path.exists() or shutil.which(tool_bin) is not None

            status = "✓ Installed" if tool_exists else "✗ Not Installed"
            status_style = "green" if tool_exists else "red"

            display_cmd = (
                install_cmd if len(install_cmd) <= 60 else install_cmd[:57] + "..."
            )

            table.add_row(
                tool_bin,
                display_cmd,
                f"[{status_style}]{status}[/{status_style}]",
            )

        console.print(table)

    async def _install_tools(self, installer: ToolInstallerRunner):
        """Install the collected tools using ToolInstallerRunner"""
        print_info("Installing Tools", "Starting tool installation...")

        try:
            await installer.run()
        except Exception as e:
            logger.error(f"Error during tool installation: {e}")

        summary = {
            "Installed": installer.installed_count,
            "Skipped": installer.skipped_count,
            "Failed": installer.failed_count,
        }
        print_info("Installation Summary", "Tool installation finished.", summary)
