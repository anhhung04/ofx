import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ofx.runner import RunContext, WorkflowRunner
from ofx.settings import (
    DEFAULT_WORKFLOWS_DIRS,
    SECRETS_DIR,
    TEMP_DIR,
    get_console,
    settings,
)
from ofx.utils.secrets import load_secrets
from ofx.utils.workflow_utils import add_workflow_dir, find_workflow

logger = logging.getLogger(settings.app_branding)
console = get_console()


def get_tmp_dir(output: str = "") -> Path:
    """Get the temporary directory for workflow runs"""
    if output and Path(output).is_dir():
        return Path(output)
    return Path(
        tempfile.mkdtemp(
            prefix=f"run_{datetime.now().strftime('%d-%m-%Y_%H%M%S')}_", dir=TEMP_DIR
        )
    )


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: list[str] | None = None,
        output: str = "",
        profile: bool = False,
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input or []
        self.output = get_tmp_dir(output)
        self.profile = profile

    async def run(self):
        import cProfile
        import pstats
        import time

        start_time = time.time()

        if self.profile:
            console.print(
                Panel(
                    "[bold yellow]Performance profiling enabled[/bold yellow]\n"
                    "[dim]Detailed timing data will be collected[/dim]",
                    title="[?] Profiling",
                    border_style="yellow",
                )
            )
            profiler = cProfile.Profile()
            profiler.enable()

        try:
            self._process_inputs()

            panel_content = [
                Text.from_markup(
                    f"[bold cyan]Workflow:[/bold cyan] {self.workflow_name}"
                ),
                Text.from_markup(
                    f"[bold cyan]Output:[/bold cyan] {self.output.as_posix()}"
                ),
            ]

            if self.input:
                panel_content.append(Text(""))
                panel_content.append(self._create_input_table())

            console.print(
                Panel(
                    Group(*panel_content),
                    title="[bold green][>] Workflow Execution[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )

            workflow = find_workflow(self.workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS))

            runner = WorkflowRunner(
                workflow,
                ctx=RunContext(
                    inputs=self.input,
                    output_path=self.output,
                    secrets=load_secrets(SECRETS_DIR),
                    workflow_dirs=add_workflow_dir(
                        DEFAULT_WORKFLOWS_DIRS, workflow.workflow_path.parent
                    ),
                ),
            )
            res = await runner.run()

            if res.status.value != "completed":
                console.print(
                    Panel(
                        f"[bold]Status:[/bold] [red]{res.status.value}[/red]\n"
                        f"[bold]Error:[/bold] [red]{res.error}[/red]",
                        title="[bold red][X] Workflow Failed[/bold red]",
                        border_style="red",
                        padding=(1, 2),
                    )
                )
            else:
                console.print(
                    Panel(
                        "[bold green]Workflow completed successfully![/bold green]",
                        title="[bold green][OK] Success[/bold green]",
                        border_style="green",
                    )
                )

            result = await runner.get_result()

        finally:
            if self.profile:
                profiler.disable()
                end_time = time.time()

                total_time = end_time - start_time

                stats = pstats.Stats(profiler)
                stats.sort_stats("cumulative")

                profile_file = self.output / "profile.prof"
                profiler.dump_stats(str(profile_file))

                console.print(
                    Panel(
                        f"[bold]Total execution time:[/bold] [cyan]{total_time:.2f}s[/cyan]\n"
                        f"[bold]Profile saved to:[/bold] [dim]{profile_file}[/dim]",
                        title="[T] Performance Summary",
                        border_style="cyan",
                    )
                )

                console.print(
                    "\n[bold cyan]Top 10 functions by cumulative time:[/bold cyan]"
                )
                stats.print_stats(10)

                console.print(
                    "\n[bold cyan]Top 10 functions by total time:[/bold cyan]"
                )
                stats.print_stats("time", 10)

        return result

    def _process_inputs(self):
        processed_inputs = {}
        for inp in self.preprocess_input or []:
            try:
                key, value = inp.split("=", 1)
            except Exception:
                raise ValueError(
                    f"Invalid input format: {inp}. Expected key=value."
                ) from None
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            if key not in processed_inputs:
                processed_inputs[key] = [value]
            else:
                processed_inputs[key].append(value)
        for key in processed_inputs:
            if len(processed_inputs[key]) == 1:
                processed_inputs[key] = processed_inputs[key][0]
        logger.debug(f"Processed inputs: {processed_inputs}")
        self.input = processed_inputs

    def _create_input_table(self) -> Table:
        """Create a Rich table for workflow inputs."""
        table = Table(
            title="[bold cyan]Inputs[/bold cyan]",
            show_header=True,
            header_style="bold cyan",
            border_style="dim cyan",
            padding=(0, 1),
        )

        table.add_column("Parameter", style="bold yellow", no_wrap=True)
        table.add_column("Value", style="white")
        table.add_column("Type", style="dim", justify="right")

        for key, value in self.input.items():
            if isinstance(value, dict):
                try:
                    formatted_value = json.dumps(value, indent=2)
                    value_type = "object"
                except (TypeError, ValueError):
                    formatted_value = str(value)
                    value_type = "object"
            elif isinstance(value, list):
                try:
                    formatted_value = json.dumps(value, indent=2)
                    value_type = "array"
                except (TypeError, ValueError):
                    formatted_value = str(value)
                    value_type = "array"
            elif isinstance(value, bool):
                formatted_value = str(value)
                value_type = "boolean"
            elif isinstance(value, (int, float)):
                formatted_value = str(value)
                value_type = "number"
            else:
                formatted_value = str(value)
                value_type = "string"

            table.add_row(key, formatted_value, value_type)

        return table
