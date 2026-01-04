import json
import logging
import tempfile
from pathlib import Path

from ofx.runner import RunContext, WorkflowRunner
from ofx.settings import DEFAULT_WORKFLOWS_DIR, SECRETS_DIR, get_console, settings
from ofx.utils.misc import find_workflow, load_secrets

logger = logging.getLogger(settings.app_branding)
console = get_console()


class FlowRunHandler:
    def __init__(
        self,
        workflow_name: str,
        input: list[str] | None = None,
        output: str | None = None,
        profile: bool = False,
    ):
        self.workflow_name = workflow_name
        self.preprocess_input = input
        self.output = (
            Path(output) if output else Path(tempfile.mkdtemp(prefix="ofx")) / "results"
        )
        self.profile = profile

    async def run(self):
        import cProfile
        import pstats
        import time

        start_time = time.time()

        if self.profile:
            console.print("🔍 Performance profiling enabled")
            profiler = cProfile.Profile()
            profiler.enable()

        try:
            self._process_inputs()
            input_display = self._render_input_as_table() if self.input else "None"
            console.print(
                f"✅ Starting to run workflow: '{self.workflow_name}' with input: {input_display}\nto output: '{self.output.as_posix()}'"
            )
            
            workflow_dirs = [DEFAULT_WORKFLOWS_DIR.absolute(), Path.cwd().absolute()]
            workflow = find_workflow(self.workflow_name, tuple(workflow_dirs))
            
            runner = WorkflowRunner(
                workflow,
                ctx=RunContext(
                    inputs=self.input,
                    output_path=self.output,
                    secrets=load_secrets(SECRETS_DIR),
                    workflow_dirs=workflow_dirs,
                ),
            )
            res = await runner.run()

            if res.status.value != "completed":
                console.print(
                    f"❌ Workflow run failed with status: {res.status}, error: {res.error}"
                )

            result = runner.get_result()

        finally:
            if self.profile:
                profiler.disable()
                end_time = time.time()

                # Print timing summary
                total_time = end_time - start_time
                console.print("\n⏱️  Performance Summary:")
                console.print(f"   Total execution time: {total_time:.2f}s")

                # Generate profile stats
                stats = pstats.Stats(profiler)
                stats.sort_stats('cumulative')

                # Save profile to file
                profile_file = self.output / "profile.prof"
                profiler.dump_stats(str(profile_file))
                console.print(f"   Profile saved to: {profile_file}")

                # Print top 10 functions by cumulative time
                console.print("   Top 10 functions by cumulative time:")
                stats.print_stats(10)

                # Print top 10 functions by total time
                console.print("   Top 10 functions by total time:")
                stats.print_stats('time', 10)

        return result

    def _process_inputs(self):
        processed_inputs = {}
        for inp in self.preprocess_input or []:
            try:
                key, value = inp.split("=", 1)
            except Exception:
                raise ValueError(f"Invalid input format: {inp}. Expected key=value.") from None
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

    def _render_input_as_table(self) -> str:
        """Renders the input data as a nicely formatted table if it contains any input."""
        from tabulate import tabulate
        if not self.input:
            return "None"

        table_data = []
        for key, value in self.input.items():
            if isinstance(value, (dict, list)):
                try:
                    formatted_value = json.dumps(value)
                except (TypeError, ValueError):
                    formatted_value = str(value)
            else:
                formatted_value = str(value)

            table_data.append([key, formatted_value])

        return "\n" + tabulate(
            table_data, headers=["Parameter", "Value"], tablefmt="grid"
        )
