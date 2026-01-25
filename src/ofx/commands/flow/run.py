import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from ofx.commands.ui_helpers import (
    execution_summary_panel,
    print_error,
    print_info,
    print_success,
    workflow_start_panel,
)
from ofx.runner import RunContext, WorkflowRunner
from ofx.runner.execution import ExecutionSummaryReporter
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
            print_info(
                "Profiling",
                "[bold yellow]Performance profiling enabled[/bold yellow]",
                {"Note": "Detailed timing data will be collected"},
            )
            profiler = cProfile.Profile()
            profiler.enable()

        try:
            self._process_inputs()

            console.print(
                workflow_start_panel(
                    self.workflow_name,
                    self.output.as_posix(),
                    inputs=self.input or None,
                )
            )

            workflow_path, workflow = find_workflow(
                self.workflow_name, tuple(DEFAULT_WORKFLOWS_DIRS)
            )

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
                print_error(
                    "Workflow Failed",
                    f"Status: {res.status.value}",
                    res.error,
                )
            else:
                print_success(
                    "Success",
                    "Workflow completed successfully!",
                )

            result = await runner.get_result()
            summary = await ExecutionSummaryReporter(runner).build()
            console.print(execution_summary_panel(summary))

        finally:
            if self.profile:
                profiler.disable()
                end_time = time.time()

                total_time = end_time - start_time

                stats = pstats.Stats(profiler)
                stats.sort_stats("cumulative")

                profile_file = self.output / "profile.prof"
                profiler.dump_stats(str(profile_file))

                print_info(
                    "Performance Summary",
                    f"Total execution time: [cyan]{total_time:.2f}s[/cyan]",
                    {"Profile saved to": profile_file},
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
