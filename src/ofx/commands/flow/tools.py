import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from rich.console import Console
from rich.table import Table

from ofx.runner import RunContext, WorkflowRunner
from ofx.runner.tool_installer import ToolInstallerRunner
from ofx.settings import TOOLS_BIN_DIR, settings

logger = logging.getLogger(settings.app_branding)
console = Console()


class ToolsInstallHandler:
    def __init__(
        self,
        workflow_name: Optional[str] = None,
        all_workflows: bool = False,
    ):
        self.workflow_name = workflow_name
        self.all_workflows = all_workflows

    async def run(self):
        """Install tools from workflow configurations"""
        if not self.workflow_name and not self.all_workflows:
            console.print(
                "[yellow]Please specify either a workflow name or use --all flag[/yellow]"
            )
            return

        workflows_to_process = []
        
        if self.all_workflows:
            workflows_to_process = self._find_all_workflows()
            if not workflows_to_process:
                console.print("[yellow]No workflow files found[/yellow]")
                return
        elif self.workflow_name:
            workflow_path = self._find_workflow_file(self.workflow_name)
            if not workflow_path:
                console.print(
                    f"[red]Workflow '{self.workflow_name}' not found[/red]"
                )
                return
            workflows_to_process = [workflow_path]

        all_tools = self._collect_tools_from_workflows(workflows_to_process)
        
        if not all_tools:
            console.print("[yellow]No tools configured in the specified workflow(s)[/yellow]")
            return

        installer = ToolInstallerRunner(
            tools=all_tools,
            ctx=RunContext(),
            parent=None,
        )
        
        self._display_tools_table(all_tools, installer)
        
        await self._install_tools(installer)

    def _find_all_workflows(self) -> List[Path]:
        """Find all workflow YAML files in the configured directories"""
        workflow_files = []
        for directory in WorkflowRunner.flows_dirs:
            if directory.exists():
                workflow_files.extend(directory.glob("*.yml"))
                workflow_files.extend(directory.glob("*.yaml"))
        return workflow_files

    def _find_workflow_file(self, workflow_name: str) -> Optional[Path]:
        """Find a specific workflow file by name using WorkflowRunner's search logic"""
        if Path(workflow_name).exists():
            return Path(workflow_name)

        for directory in WorkflowRunner.flows_dirs:
            for ext in [".yml", ".yaml"]:
                path = directory / f"{workflow_name.rstrip('.yml').rstrip('.yaml')}{ext}"
                if path.exists():
                    return path
        
        return None

    def _collect_tools_from_workflows(
        self, workflow_paths: List[Path]
    ) -> Dict[str, str]:
        """Collect all unique tools from the given workflows"""
        all_tools = {}
        
        for workflow_path in workflow_paths:
            try:
                with open(workflow_path, "r") as f:
                    workflow_data = yaml.safe_load(f)
                
                tools = workflow_data.get("tools", {})
                if not tools:
                    tools = workflow_data.get("defaults", {}).get("tools", {})
                
                if tools and isinstance(tools, dict):
                    for tool_bin, tool_config in tools.items():
                        if isinstance(tool_config, str):
                            all_tools[tool_bin] = tool_config
                        elif isinstance(tool_config, dict):
                            install_cmd = tool_config.get("install", "")
                            if install_cmd:
                                all_tools[tool_bin] = install_cmd
                    
                    logger.debug(
                        f"Found {len(tools)} tools in workflow: {workflow_path.name}"
                    )
            except Exception as e:
                logger.error(f"Error loading workflow {workflow_path}: {e}")
                console.print(
                    f"[yellow]Warning: Could not load {workflow_path.name}: {e}[/yellow]"
                )
        
        return all_tools

    def _display_tools_table(self, tools: Dict[str, str], installer: ToolInstallerRunner):
        """Display tools in a formatted table with resolved templates"""
        table = Table(title="Tools to Install", show_header=True, header_style="bold cyan")
        table.add_column("Tool", style="green")
        table.add_column("Install Command", style="yellow")
        table.add_column("Status", style="blue")
        
        for tool_bin, install_cmd in tools.items():
            resolved_cmd = installer._resolve_template(install_cmd)
            tool_path = TOOLS_BIN_DIR / tool_bin
            tool_exists = tool_path.exists() or shutil.which(tool_bin) is not None
            
            status = "✓ Installed" if tool_exists else "✗ Not Installed"
            status_style = "green" if tool_exists else "red"
            table.add_row(
                tool_bin,
                resolved_cmd,
                f"[{status_style}]{status}[/{status_style}]",
            )
        
        console.print(table)

    async def _install_tools(self, installer: ToolInstallerRunner):
        """Install the collected tools using ToolInstallerRunner"""
        console.print("\n[bold]Installing tools...[/bold]\n")
        
        try:
            await installer.run()
        except Exception as e:
            logger.error(f"Error during tool installation: {e}")
        
        console.print("\n[bold]Installation Summary:[/bold]")
        console.print(f"  Installed: [green]{installer.installed_count}[/green]")
        console.print(f"  Skipped: [yellow]{installer.skipped_count}[/yellow]")
        if installer.failed_count > 0:
            console.print(f"  Failed: [red]{installer.failed_count}[/red]")
